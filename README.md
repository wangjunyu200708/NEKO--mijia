# 米家智能设备插件

## 功能特性
- 连接米家云服务（用户名密码/二维码登录）
- 自动发现设备
- 获取设备属性
- 设置设备属性
- 调用设备动作
- 设备状态监控

## 配置说明

### 配置文件位置
`config/mijia.json`

### 配置示例
```json
{
  "username": "your_phone_or_email",
  "password": "your_password",
  "enableQR": false,
  "log_level": "INFO",
  "auto_connect": false,
  "device_cache_ttl": 300
}