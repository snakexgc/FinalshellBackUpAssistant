# Finalshell 配置文件备份工具

基于 WebDAV 云端存储的 Finalshell 配置文件备份工具。

## 功能特性

- **WebDAV 云端存储** - 支持将备份文件存储到 WebDAV 服务器
- **本地完整备份** - 完整打包当前配置进行备份
- **本地/云端优先备份** - 基于已有云端备份，按选定策略合并本地文件
- **云端恢复** - 从 WebDAV 下载备份并恢复
- **备份管理** - 查看、删除云端备份文件
- **连接密码解密** - 选择单个 JSON 或整个 `conn` 文件夹，显示可复制的连接信息和解密后的密码

## 项目结构

```
FinalshellBackUpAssistant/
├── main.py                 # 程序入口
├── requirements.txt        # 依赖列表
├── core/                   # 核心模块
│   ├── __init__.py
│   ├── webdav_client.py    # WebDAV客户端封装
│   ├── backup_manager.py   # 备份管理逻辑
│   └── finalshell_decryptor.py # FinalShell密码解密逻辑
├── ui/                     # 界面模块
│   ├── __init__.py
│   ├── main_window.py      # 主窗口
│   ├── webdav_frame.py     # WebDAV配置面板
│   ├── backup_frame.py     # 备份操作面板
│   └── decrypt_frame.py    # 配置解密面板
└── utils/                  # 工具模块
    ├── __init__.py
    └── logger.py           # 日志工具
```

## 备份文件命名规则

- 所有备份：`YYYYMMDDHHMMSS.zip`


### WebDAV 目录结构

备份文件存储在 WebDAV 服务器的 `/Finalshell_BackUp` 目录下。

## 依赖要求

- Python 3.8+
- requests >= 2.28.0
- webdavclient3 >= 3.14.6
- tkinter（Python 标准库）
