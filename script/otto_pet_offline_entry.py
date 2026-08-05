# -*- coding: utf-8 -*-
"""离线版入口：在导入主程序前标记为离线模式（关闭 AiChat）。"""
import os

os.environ["OTTO_PET_MODE"] = "offline"

import otto_pet  # noqa: E402


if __name__ == "__main__":
    otto_pet.main()
