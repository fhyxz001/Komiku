# Komiku

扫描漫画文件夹大小，Web 可视化管理。零第三方依赖，Python 标准库实现。

## 功能

- **大小可视化**：条形图 + 饼图双视图，按大小降序，自动 GB/MB/TB 换算
- **删除**：二次确认 → `shutil.rmtree` 删除整个子文件夹
- **刷新**：重新扫描获取最新数据
- **错误处理**：目录不存在 / 命令失败 / 非法请求，界面明确提示
- **安全**：删除接口校验文件夹名（禁 `/` `\` `..`），`realpath` 越界检测，仅允许删 `MANGA_DIR` 的直接子目录

## 快速开始

```bash
# 本地预览（模拟数据，不执行 du）
MOCK=1 PORT=8090 python3 app.py

# 连接真实 NAS 目录
MANGA_DIR=/vol1/1000/Manga PORT=8080 python3 app.py
```

浏览器访问 `http://127.0.0.1:8090`。

## 技术说明

原指令 `du -sh --block-size=G` 会把每个目录四舍五入到整 G，小文件夹全部显示为 `1G`，丢失分辨率。
后端改用 `du -sb`（精确字节），前端再换算为可读单位，可视化更准确。

## 文件结构

```
Komiku/
├── app.py                          # 后端（标准库 http.server）
├── Dockerfile                      # Docker 镜像构建
├── static/
│   └── index.html                  # 前端（vanilla JS）
├── .github/workflows/
│   └── docker-build.yml            # CI：自动编译离线镜像
└── README.md
```

## 部署方式

### 方式一：直接运行（NAS / Linux）

```bash
cd /opt/komiku
# 后台运行
nohup python3 app.py > komiku.log 2>&1 &
```

### 方式二：Docker

```bash
docker build -t komiku .
docker run -d -p 8080:8080 -v /vol1/1000/Manga:/vol1/1000/Manga komiku
```

### 方式三：Docker 离线包

GitHub Actions 自动构建产物 `komiku.tar.gz`，在离线 NAS 导入：

```bash
docker load -i komiku.tar.gz
docker run -d -p 8080:8080 komiku
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/`            | 前端页面 |
| GET  | `/api/folders` | `{ok, dir, mock, count, total_bytes, folders:[{name,path,size_bytes}]}` |
| POST | `/api/delete`  | `{"name":"子文件夹名"}` → `{ok, deleted}` |

## 配置项（环境变量）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MANGA_DIR` | `/vol1/1000/Manga` | 漫画根目录 |
| `HOST` | `0.0.0.0` | 监听地址 |
| `PORT` | `8080` | 监听端口 |
| `MOCK` | (空) | 设为 `1` 启用模拟数据 |

## 安全提示

- 删除操作**不可恢复**，确认弹窗已强制二次确认
- 服务无认证，**仅在内网/可信网络运行**，不要暴露到公网
- 删除仅限 `MANGA_DIR` 的直接子目录，已防路径穿越攻击
