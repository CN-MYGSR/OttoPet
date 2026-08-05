# 电棍桌宠一键打包脚本：生成两个 exe、两个 Inno Setup 安装程序、两个 MSI
# 用法：powershell -ExecutionPolicy Bypass -File installer\build_all.ps1

param(
    [switch]$KeepWixBuild
)

$ErrorActionPreference = "Stop"

$root        = "D:\OttoPet"
$scriptDir   = Join-Path $root "script"
$installerDir= Join-Path $root "installer"
$releaseDir  = Join-Path $root "release"
$stagingDir  = Join-Path $root "staging"
$buildDir    = Join-Path $root "build"
$distDir     = Join-Path $root "dist"
$wixBuildDir = Join-Path $installerDir "build"
$toolsDir    = Join-Path $env:LOCALAPPDATA "OttoPetBuildTools"
$wixTools    = Join-Path $toolsDir "wix3\tools"
$iscc        = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"

$version = "1.0.0"

function Remove-Dir([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

# ---------- 1. 重新打包两个 exe ----------
Write-Host "==> 打包 exe（标准版 / 离线版）"
Remove-Dir $distDir
Remove-Dir $buildDir
python -m PyInstaller --noconfirm --onefile --windowed --name otto_pet `
    --icon (Join-Path $scriptDir "otto_icon.ico") `
    --distpath $distDir --workpath $buildDir (Join-Path $scriptDir "otto_pet.py")
python -m PyInstaller --noconfirm --onefile --windowed --name otto_pet_offline `
    --icon (Join-Path $scriptDir "otto_icon.ico") `
    --distpath $distDir --workpath $buildDir (Join-Path $scriptDir "otto_pet_offline_entry.py")

# 同步根目录便携版 exe
Copy-Item -LiteralPath (Join-Path $distDir "otto_pet.exe") -Destination (Join-Path $root "otto_pet.exe") -Force

# ---------- 2. 组装安装目录 ----------
Write-Host "==> 组装安装内容"
Remove-Dir $stagingDir
Push-Location $installerDir
foreach ($variant in @("standard", "offline")) {
    $dir = Join-Path $stagingDir $variant
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    $exeName = if ($variant -eq "offline") { "otto_pet_offline.exe" } else { "otto_pet.exe" }
    Copy-Item -LiteralPath (Join-Path $distDir $exeName) -Destination (Join-Path $dir "otto_pet.exe")
    Copy-Item -LiteralPath (Join-Path $root "assets") -Destination $dir -Recurse
    Copy-Item -LiteralPath (Join-Path $root "README.md") -Destination (Join-Path $dir "使用说明.txt")
}

# ---------- 3. Inno Setup 安装程序 ----------
Write-Host "==> 编译 Inno Setup 安装程序"
New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
& $iscc ("/DAppVersion=" + $version) "/DVariant=standard" (Join-Path $installerDir "otto_pet.iss")
& $iscc ("/DAppVersion=" + $version) "/DVariant=offline" (Join-Path $installerDir "otto_pet.iss")

# ---------- 4. WiX MSI ----------
Write-Host "==> 编译 MSI 安装程序"
Remove-Dir $wixBuildDir
New-Item -ItemType Directory -Path $wixBuildDir -Force | Out-Null

function New-ComponentsWxs {
    param([string]$StagingDir, [string]$OutFile, [string]$RegKey)

    $files = Get-ChildItem -LiteralPath $StagingDir -Recurse -File
    $fileList = @()
    $i = 0
    foreach ($f in $files) {
        $rel = $f.FullName.Substring($StagingDir.Length).TrimStart("\")
        $relDir = Split-Path $rel -Parent
        $name = Split-Path $rel -Leaf
        if ($rel -eq "otto_pet.exe") { $id = "ottoExe" }
        elseif ($rel -eq "使用说明.txt") { $id = "readme" }
        else { $id = "file" + $i }
        $i++
        $fileList += [PSCustomObject]@{ Rel = $rel; RelDir = $relDir; Name = $name; Id = $id; Full = $f.FullName }
    }

    $leafDirs = @($fileList | ForEach-Object { if ($_.RelDir -ne "") { $_.RelDir } } | Sort-Object -Unique)
    $dirSet = New-Object 'System.Collections.Generic.HashSet[string]'
    foreach ($ld in $leafDirs) {
        $parts = $ld -split "\\"
        for ($k = 1; $k -le $parts.Count; $k++) {
            [void]$dirSet.Add(($parts[0..($k - 1)] -join '\'))
        }
    }
    $dirs = @($dirSet) | Sort-Object

    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine('<?xml version="1.0" encoding="UTF-8"?>')
    [void]$sb.AppendLine('<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">')
    [void]$sb.AppendLine('  <Fragment>')
    [void]$sb.AppendLine('    <DirectoryRef Id="INSTALLFOLDER">')

    $dirIds = @{ "" = "INSTALLFOLDER" }
    $children = @{ "" = @() }
    $dirCounter = 0
    foreach ($d in $dirs) {
        $parts = $d -split "\\"
        $parent = if ($parts.Count -gt 1) { ($parts[0..($parts.Count - 2)] -join '\') } else { "" }
        if (-not $children.ContainsKey($parent)) { $children[$parent] = @() }
        $children[$parent] += $d
        $dirCounter++
        $dirIds[$d] = "dir" + $dirCounter
    }

    function Emit-DirTree {
        param(
            [string]$Path,
            [int]$Depth,
            [hashtable]$Children,
            [hashtable]$DirIds,
            [System.Text.StringBuilder]$Sb
        )
        $indent = "      " + ("  " * $Depth)
        foreach ($child in ($Children[$Path] | Sort-Object)) {
            [void]$Sb.AppendLine($indent + '<Directory Id="' + $DirIds[$child] + '" Name="' + (Split-Path $child -Leaf) + '">')
            Emit-DirTree -Path $child -Depth ($Depth + 1) -Children $Children -DirIds $DirIds -Sb $Sb
            [void]$Sb.AppendLine($indent + "</Directory>")
        }
    }
    Emit-DirTree -Path "" -Depth 0 -Children $children -DirIds $dirIds -Sb $sb
    [void]$sb.AppendLine("    </DirectoryRef>")

    $md5 = [System.Security.Cryptography.MD5]::Create()
    foreach ($item in $fileList) {
        $hash = $md5.ComputeHash([System.Text.Encoding]::UTF8.GetBytes("ottopet:" + $item.Rel))
        $guid = (New-Object System.Guid (,$hash)).ToString("B").ToUpper()
        [void]$sb.AppendLine('    <Component Id="cmp' + $item.Id + '" Guid="' + $guid + '" Directory="' + $dirIds[$item.RelDir] + '">')
        [void]$sb.AppendLine('      <File Id="' + $item.Id + '" Name="' + $item.Name + '" Source="' + $item.Full + '"/>')
        [void]$sb.AppendLine('      <RegistryValue Root="HKCU" Key="' + $RegKey + '" Name="' + $item.Id + '" Type="integer" Value="1" KeyPath="yes"/>')
        [void]$sb.AppendLine("    </Component>")
    }

    # 卸载时清理安装目录（满足 ICE64 校验）
    if ($dirs.Count -gt 0) {
        $hash = $md5.ComputeHash([System.Text.Encoding]::UTF8.GetBytes("ottopet:removedirs"))
        $guid = (New-Object System.Guid (,$hash)).ToString("B").ToUpper()
        [void]$sb.AppendLine('    <Component Id="cmpRemoveDirs" Guid="' + $guid + '" Directory="INSTALLFOLDER">')
        foreach ($d in $dirs) {
            [void]$sb.AppendLine('      <RemoveFolder Id="rf' + $dirIds[$d] + '" Directory="' + $dirIds[$d] + '" On="uninstall"/>')
        }
        [void]$sb.AppendLine('      <RegistryValue Root="HKCU" Key="' + $RegKey + '" Name="removedirs" Type="integer" Value="1" KeyPath="yes"/>')
        [void]$sb.AppendLine("    </Component>")
    }

    [void]$sb.AppendLine('  </Fragment>')
    [void]$sb.AppendLine('  <Fragment>')
    [void]$sb.AppendLine('    <ComponentGroup Id="AppComponents">')
    foreach ($item in $fileList) {
        [void]$sb.AppendLine('      <ComponentRef Id="cmp' + $item.Id + '"/>')
    }
    if ($dirs.Count -gt 0) {
        [void]$sb.AppendLine('      <ComponentRef Id="cmpRemoveDirs"/>')
    }
    [void]$sb.AppendLine('    </ComponentGroup>')
    [void]$sb.AppendLine('  </Fragment>')
    [void]$sb.AppendLine("</Wix>")
    Set-Content -LiteralPath $OutFile -Value $sb.ToString() -Encoding UTF8
}

foreach ($variant in @("standard", "offline")) {
    $regKey = if ($variant -eq "offline") { "Software\OttoPet\Offline" } else { "Software\OttoPet\Standard" }
    New-ComponentsWxs -StagingDir (Join-Path $stagingDir $variant) `
        -OutFile (Join-Path $wixBuildDir ($variant + "_components.wxs")) -RegKey $regKey

    & (Join-Path $wixTools "candle.exe") -nologo ("-dVariant=" + $variant) ("-dVersion=" + $version) `
        -out (Join-Path $wixBuildDir ($variant + "_main.wixobj")) (Join-Path $installerDir "otto_pet_msi.wxs")
    & (Join-Path $wixTools "candle.exe") -nologo `
        -out (Join-Path $wixBuildDir ($variant + "_components.wixobj")) (Join-Path $wixBuildDir ($variant + "_components.wxs"))

    $msiName = "OttoPet-" + $(if ($variant -eq "offline") { "离线版" } else { "标准版" }) + "-" + $version + ".msi"
    & (Join-Path $wixTools "light.exe") -nologo `
        -out (Join-Path $releaseDir $msiName) `
        (Join-Path $wixBuildDir ($variant + "_main.wixobj")) `
        (Join-Path $wixBuildDir ($variant + "_components.wixobj"))
}
Pop-Location

# ---------- 5. 校验和 ----------
Write-Host "==> 生成校验和"
$lines = Get-ChildItem -LiteralPath $releaseDir -File | Sort-Object Name | ForEach-Object {
    (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower() + "  " + $_.Name
}
Set-Content -LiteralPath (Join-Path $releaseDir "SHA256SUMS.txt") -Value $lines -Encoding UTF8

# ---------- 清理中间目录 ----------
Remove-Dir $distDir
Remove-Dir $buildDir
Remove-Dir $stagingDir
if (-not $KeepWixBuild) {
    Remove-Dir $wixBuildDir
}

Write-Host ""
Write-Host "打包完成，输出目录：$releaseDir"
Get-ChildItem -LiteralPath $releaseDir -File | Select-Object Name, @{N="SizeMB";E={[math]::Round($_.Length/1MB,1)}} | Format-Table -AutoSize
