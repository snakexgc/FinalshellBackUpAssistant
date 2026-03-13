# Finalshell 配置文件备份工具

基于 WebDAV 云端存储的 Finalshell 配置文件备份工具。

## 功能特性

- **WebDAV 云端存储** - 支持将备份文件存储到 WebDAV 服务器
- **增量备份** - 基于已有备份进行增量更新
- **覆盖备份** - 完整打包当前配置进行备份
- **云端恢复** - 从 WebDAV 下载备份并恢复
- **备份管理** - 查看、删除云端备份文件

## 项目结构

```
FinalshellBackUpAssistant/
├── main.py                 # 程序入口
├── requirements.txt        # 依赖列表
├── core/                   # 核心模块
│   ├── __init__.py
│   ├── webdav_client.py    # WebDAV客户端封装
│   └── backup_manager.py   # 备份管理逻辑
├── ui/                     # 界面模块
│   ├── __init__.py
│   ├── main_window.py      # 主窗口
│   ├── webdav_frame.py     # WebDAV配置面板
│   └── backup_frame.py     # 备份操作面板
└── utils/                  # 工具模块
    ├── __init__.py
    └── logger.py           # 日志工具
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行方式

**正确方式（通过 main.py 运行）：**

```bash
python main.py
```

**注意：** 不要直接运行 core/ 或 ui/ 目录下的单个文件，因为使用了包相对导入，直接运行会导致导入错误。

## 使用说明

1. **配置 WebDAV**
   - 输入 WebDAV 服务器地址
   - 输入用户名和密码
   - 点击"登录WebDAV"按钮

2. **增量备份**
   - 选择"增量模式"
   - 选择基准备份文件（可选）
   - 点击"备份"按钮

3. **覆盖备份**
   - 选择"覆盖模式"
   - 点击"备份"按钮

4. **恢复备份**
   - 从列表中选择要恢复的备份文件
   - 点击"恢复"按钮

5. **删除备份**
   - 从列表中选择要删除的备份文件
   - 点击"删除选中备份"按钮

## 备份文件命名规则

- 增量备份：`年月日时分秒_增量备份.zip`
- 覆盖备份：`年月日时分秒_覆盖备份.zip`

## 技术说明

### 关于相对导入错误

如果在终端看到类似下面的错误：
```
ImportError: attempted relative import with no known parent package
```

这是因为直接运行了子模块文件（如 `python core/backup_manager.py`）。
**解决方法：** 始终通过 `python main.py` 运行程序。

### WebDAV 目录结构

备份文件存储在 WebDAV 服务器的 `/Finalshell_BackUp` 目录下。

## 依赖要求

- Python 3.8+
- requests >= 2.28.0
- webdavclient3 >= 3.14.6
- tkinter（Python 标准库）