# FinalShell 配置备份、同步与解密工具

基于 WebDAV 的 FinalShell 配置管理工具。

## 功能

- WebDAV 云端备份、恢复和备份文件管理
- 本地/云端优先的备份及恢复策略
- `config.json` 与 `conn` 文件夹实时同步
- 云端基准或本地基准的首次精确镜像
- 云端同步目录为空时自动使用本地基准
- 进入监听状态后从工具中启动 FinalShell
- FinalShell 连接信息与密码解密
- 保存 WebDAV 和 FinalShell 路径，启动时自动恢复上次设置

## 同步规则

同步内容位于 WebDAV 的 `Finalshell_BackUp/sync` 目录：

```text
Finalshell_BackUp/
└── sync/
    ├── config.json
    └── conn/
```

- 云端基准：云端文件覆盖本地同名文件；云端独有文件下载到本地；本地独有文件删除。
- 本地基准：本地文件覆盖云端同名文件；本地独有文件上传到云端；云端独有文件删除。
- 若云端没有 `config.json` 和 `conn` 中的文件，即使选择云端基准，也会自动按本地基准初始化。
- 首次同步完成后监听本地 `config.json` 和 `conn`，本地的新增、修改和删除会实时同步到云端。

为避免首次同步时 FinalShell 同时写入配置，请先启动同步，界面显示“正在监听”后再点击“启动 FinalShell 程序”。

## 配置保存

点击 WebDAV 区域中的“保存配置”，程序会在自身同级目录写入
`FinalshellBackUpAssistant.json`。其中包含 WebDAV 地址、用户名、密码和
FinalShell 安装路径。配置目前以明文保存，请妥善保管该文件。

旧版同级 `config.json` 仍可读取；新的保存操作只会写入独立设置文件，避免工具放在 FinalShell 安装目录时覆盖 FinalShell 自身的 `config.json`。

## 依赖

- Python 3.10+
- requests >= 2.34.2
- webdavclient3 >= 3.14.7
- pycryptodome >= 3.23.0
- watchdog >= 6.0.0

安装并运行：

```powershell
pip install -r requirements.txt
python main.py
```

## WebDAV 根目录

备份恢复文件和 `sync` 子目录统一放在 WebDAV 的 `Finalshell_BackUp` 目录中。
所有 WebDAV HTTP 请求的超时时间为 10 秒。
