"""米家插件单元测试"""

import pytest
import sys
import json
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

# 添加项目根目录
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from plugin.plugins.mijia import MijiaPlugin


class MockPluginContext:
    """模拟的插件上下文"""
    
    def __init__(self, tmp_path=None):
        self.plugin_id = "mijia"
        self.config_path = Path("config/mijia.json") if not tmp_path else tmp_path / "mijia.json"
        self.status_updates = []
        self.messages = []
        
    def info(self, msg):
        print(f"[INFO] {msg}")
    
    def error(self, msg):
        print(f"[ERROR] {msg}")
    
    def warning(self, msg):
        print(f"[WARN] {msg}")
    
    def debug(self, msg):
        print(f"[DEBUG] {msg}")
    
    def exception(self, msg):
        print(f"[EXCEPTION] {msg}")
    
    def update_status(self, status):
        self.status_updates.append(status)
    
    def push_message(self, **kwargs):
        self.messages.append(kwargs)


@pytest.fixture
def mock_context(tmp_path):
    """提供模拟的插件上下文"""
    return MockPluginContext(tmp_path)


@pytest.fixture
def plugin(mock_context):
    """创建插件实例"""
    with patch('plugin.plugins.mijia.MijiaAdapter') as mock_adapter_class:
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        plugin = MijiaPlugin(mock_context)
        return plugin


class TestMijiaPlugin:
    """米家插件测试类"""
    
    def test_plugin_initialization(self, plugin, mock_context):
        """测试插件初始化"""
        assert plugin.ctx == mock_context
        assert plugin.connected == False
        assert plugin.device_cache == {}
        assert plugin.config is not None
        
    def test_config_loading(self, plugin, tmp_path):
        """测试配置加载"""
        # 创建测试配置文件
        config_file = tmp_path / "mijia.json"
        test_config = {
            "username": "test_user",
            "password": "test_pass",
            "enableQR": True,
            "log_level": "DEBUG",
            "auto_connect": False,
            "device_cache_ttl": 300
        }
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(test_config, f)
        
        # 重新加载配置
        plugin.config_path = config_file
        plugin._load_config()
        
        assert plugin.config["username"] == "test_user"
        assert plugin.config["enableQR"] == True
        
    def test_config_saving(self, plugin, tmp_path):
        """测试配置保存"""
        config_file = tmp_path / "mijia.json"
        plugin.config_path = config_file
        plugin.config = {
            "username": "new_user",
            "password": "new_pass",
            "enableQR": False
        }
        
        plugin._save_config()
        
        # 验证文件已创建
        assert config_file.exists()
        
        # 验证内容
        with open(config_file, 'r', encoding='utf-8') as f:
            saved_config = json.load(f)
        
        assert saved_config["username"] == "new_user"
        assert saved_config["enableQR"] == False
        
    @pytest.mark.asyncio
    async def test_connect_without_adapter(self, plugin):
        """测试未初始化适配器时的连接"""
        plugin.adapter = None
        result = await plugin.connect()
        
        assert result["success"] == False
        assert "适配器未初始化" in result["error"]
        
    @pytest.mark.asyncio
    async def test_connect_success(self, plugin):
        """测试连接成功"""
        # 模拟适配器
        mock_adapter = AsyncMock()
        mock_adapter.connect.return_value = True
        mock_adapter.connected = True
        mock_adapter.device_count = 5
        plugin.adapter = mock_adapter
        
        result = await plugin.connect()
        
        assert result["success"] == True
        assert plugin.connected == True
        assert len(plugin.ctx.status_updates) > 0
        
    @pytest.mark.asyncio
    async def test_connect_failure(self, plugin):
        """测试连接失败"""
        mock_adapter = AsyncMock()
        mock_adapter.connect.return_value = False
        plugin.adapter = mock_adapter
        
        result = await plugin.connect()
        
        assert result["success"] == False
        assert plugin.connected == False
        
    @pytest.mark.asyncio
    async def test_discover_devices_not_connected(self, plugin):
        """测试未连接时发现设备"""
        plugin.connected = False
        result = await plugin.discover_devices()
        
        assert result["success"] == False
        assert "未连接到米家云服务" in result["error"]
        
    @pytest.mark.asyncio
    async def test_discover_devices_success(self, plugin):
        """测试发现设备成功"""
        # 模拟设备和适配器
        mock_device = Mock()
        mock_device.did = "device_123"
        mock_device.name = "Test Device"
        mock_device.model = "test.model"
        mock_device.online = True
        
        mock_adapter = AsyncMock()
        mock_adapter.discover_devices.return_value = [mock_device]
        plugin.adapter = mock_adapter
        plugin.connected = True
        
        result = await plugin.discover_devices()
        
        assert result["success"] == True
        assert result["count"] == 1
        assert result["devices"][0]["did"] == "device_123"
        assert "device_123" in plugin.device_cache
        
    @pytest.mark.asyncio
    async def test_get_devices_from_cache(self, plugin):
        """测试从缓存获取设备"""
        # 填充缓存
        plugin.device_cache = {
            "dev1": {"did": "dev1", "name": "Device 1"},
            "dev2": {"did": "dev2", "name": "Device 2"}
        }
        plugin.last_discovery_time = datetime.now()
        
        result = await plugin.get_devices()
        
        assert result["success"] == True
        assert result["count"] == 2
        assert result["cached"] == True
        
    @pytest.mark.asyncio
    async def test_get_devices_auto_discover(self, plugin):
        """测试缓存为空时自动发现"""
        plugin.device_cache = {}
        
        # 模拟discover_devices方法
        async def mock_discover(**kwargs):
            return {"success": True, "devices": []}
        
        plugin.discover_devices = mock_discover
        
        result = await plugin.get_devices()
        
        assert result["success"] == True
        
    @pytest.mark.asyncio
    async def test_set_property_value(self, plugin):
        """测试设置属性值"""
        mock_adapter = AsyncMock()
        mock_adapter.set_property_value.return_value = True
        plugin.adapter = mock_adapter
        plugin.connected = True
        
        result = await plugin.set_property_value(
            device_id="dev_123",
            siid=2,
            piid=1,
            value=True
        )
        
        assert result["success"] == True
        assert result["device_id"] == "dev_123"
        assert result["value"] == True
        
        # 验证消息推送
        assert len(plugin.ctx.messages) > 0
        
    @pytest.mark.asyncio
    async def test_search_devices(self, plugin):
        """测试搜索设备"""
        # 准备缓存数据
        plugin.device_cache = {
            "dev1": {"did": "dev1", "name": "Living Room Light", "model": "light", "online": True},
            "dev2": {"did": "dev2", "name": "Bedroom Light", "model": "light", "online": False},
            "dev3": {"did": "dev3", "name": "Air Conditioner", "model": "ac", "online": True}
        }
        
        # 测试名称搜索
        result = await plugin.search_devices(query="light")
        assert result["count"] == 2
        
        # 测试在线过滤
        result = await plugin.search_devices(online_only=True)
        assert result["count"] == 2  # dev1 和 dev3 在线
        
        # 测试组合搜索
        result = await plugin.search_devices(query="light", online_only=True)
        assert result["count"] == 1  # 只有 Living Room Light 在线
        
    def test_check_connected(self, plugin):
        """测试连接状态检查"""
        plugin.connected = True
        plugin.adapter = Mock()
        assert plugin._check_connected() == True
        
        plugin.connected = False
        assert plugin._check_connected() == False
        
        plugin.connected = True
        plugin.adapter = None
        assert plugin._check_connected() == False
        
    def test_not_connected_response(self, plugin):
        """测试未连接响应"""
        response = plugin._not_connected_response()
        assert response["success"] == False
        assert "未连接到米家云服务" in response["error"]
        
    @pytest.mark.asyncio
    async def test_lifecycle_startup(self, plugin):
        """测试生命周期启动"""
        # 模拟配置
        plugin.config = {"auto_connect": False}
        
        result = plugin.startup()
        
        assert result["status"] == "started"
        assert plugin.adapter is not None
        assert len(plugin.ctx.status_updates) > 0
        
    @pytest.mark.asyncio
    async def test_lifecycle_shutdown(self, plugin):
        """测试生命周期关闭"""
        plugin.adapter = AsyncMock()
        plugin.connected = True
        
        result = plugin.shutdown()
        
        assert result["status"] == "stopped"
        
    @pytest.mark.asyncio
    async def test_heartbeat_connected(self, plugin):
        """测试心跳 - 已连接"""
        plugin.connected = True
        plugin.adapter = Mock()
        plugin.adapter.connected = True
        
        result = await plugin.heartbeat()
        
        assert result["checked"] == True
        assert plugin.connected == True
        
    @pytest.mark.asyncio
    async def test_heartbeat_disconnected(self, plugin):
        """测试心跳 - 连接断开"""
        plugin.connected = True
        plugin.adapter = Mock()
        plugin.adapter.connected = False
        
        result = await plugin.heartbeat()
        
        assert result["checked"] == True
        assert plugin.connected == False
        assert len(plugin.ctx.messages) > 0  # 应该有断开连接的消息
        
    @pytest.mark.asyncio
    async def test_update_config(self, plugin):
        """测试更新配置"""
        plugin.config = {
            "username": "old_user",
            "password": "old_pass",
            "enableQR": False
        }
        
        # 模拟保存方法
        plugin._save_config = Mock()
        
        result = await plugin.update_config(
            username="new_user",
            enableQR=True
        )
        
        assert result["success"] == True
        assert result["updated"] == True
        assert plugin.config["username"] == "new_user"
        assert plugin.config["enableQR"] == True
        assert plugin.config["password"] == "old_pass"  # 未改变
        
        plugin._save_config.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_get_status(self, plugin):
        """测试获取状态"""
        plugin.connected = True
        plugin.device_cache = {"dev1": {}, "dev2": {}}
        plugin.config = {
            "username": "test_user",
            "password": "secret",
            "enableQR": False
        }
        
        result = await plugin.get_status()
        
        assert result["success"] == True
        assert result["connected"] == True
        assert result["device_count"] == 2
        
        # 检查用户名显示（实际实现可能会隐藏部分）
        username = result["config"]["username"]
        assert "test" in username or "tes" in username  # 灵活匹配
        assert "password" not in result["config"]  # 密码不应返回
        print(f"✓ 状态测试通过，用户名显示为: {username}")
