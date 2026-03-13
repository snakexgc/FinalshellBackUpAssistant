"""
Finalshell配置文件备份工具
主程序入口

功能：
- 支持WebDAV云端存储
- 增量备份和覆盖备份
- 从云端恢复备份
- 管理云端备份文件

作者：Assistant
版本：3.0
"""

import sys
import os

# 添加当前目录到路径，确保可以导入本地模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui import MainWindow


def main():
    """主函数"""
    app = MainWindow()
    app.run()


if __name__ == "__main__":
    main()
