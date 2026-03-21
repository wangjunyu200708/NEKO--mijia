"""米家智能设备插件 - 主类"""

import json
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from plugin.sdk.base import NekoPluginBase
from plugin.sdk.decorators import neko_plugin, plugin_entry, lifecycle, timer_interval

from .adapter.mijia_adapter import MijiaAdapter
from .config.mijia_config import load_mijia_config
from .utils.logger import get_logger

logger = get_logger(__name__)

@neko_plugin
class MijiaPlugin(NekoPluginBase):
    """米家智能设备插件"""
    
    def __init__(self, ctx: Any):
        super().__init__(ctx)
        self.ctx = ctx
        self.logger = logger
        self.config = None
        self.adapter: Optional[MijiaAdapter] = None
        self.connected = False
        self.device_cache = {}
        self.last_discovery_time = None
        
        # 设备标识持久化文件
        self.devices_file = ctx.config_path.parent / "devices.json"
        self._load_device_cache()
        
        # 从上下文获取配置路径
        self.config_path = ctx.config_path.parent / "mijia.json"
        self._load_config()
        
        self.logger.info("米家插件初始化完成")
    
    def _load_device_cache(self):
        """从文件加载设备缓存"""
        try:
            if self.devices_file.exists():
                with open(self.devices_file, 'r', encoding='utf-8') as f:
                    self.device_cache = json.load(f)
                self.logger.info(f"已加载 {len(self.device_cache)} 个设备缓存")
        except Exception as e:
            self.logger.error(f"加载设备缓存失败: {e}")
            self.device_cache = {}
    
    def _save_device_cache(self):
        """保存设备缓存到文件"""
        try:
            with open(self.devices_file, 'w', encoding='utf-8') as f:
                json.dump(self.device_cache, f, ensure_ascii=False, indent=2)
            self.logger.info(f"已保存 {len(self.device_cache)} 个设备缓存")
        except Exception as e:
            self.logger.error(f"保存设备缓存失败: {e}")
    
    def _update_device_properties_cache(self, device_id: str, properties: List):
        """更新设备属性缓存（包含 siid/piid）"""
        if device_id not in self.device_cache:
            return
        
        device_info = self.device_cache[device_id]
        properties_info = {}
        
        for prop in properties:
            prop_info = {
                "name": prop.name,
                "description": prop.desc,
                "type": prop.type,
                "rw": prop.rw,
                "unit": prop.unit,
                "siid": getattr(prop, 'siid', None),
                "piid": getattr(prop, 'piid', None),
                "range": getattr(prop, 'range', None),
                "value_list": getattr(prop, 'value_list', None)
            }
            properties_info[prop.name] = prop_info
        
        device_info["properties"] = properties_info
        device_info["last_update"] = datetime.now().isoformat()
        self.device_cache[device_id] = device_info
        
        # 保存到文件
        self._save_device_cache()
        self.logger.info(f"已更新设备 {device_id} 的属性缓存（含 siid/piid）")
    
    def _update_device_actions_cache(self, device_id: str, actions: List):
        """更新设备动作缓存（包含 siid/aiid）"""
        if device_id not in self.device_cache:
            return
        
        device_info = self.device_cache[device_id]
        actions_info = {}
        
        for action in actions:
            action_info = {
                "name": action.name,
                "description": action.desc,
                "siid": getattr(action, 'siid', None),
                "aiid": getattr(action, 'aiid', None)
            }
            actions_info[action.name] = action_info
        
        device_info["actions"] = actions_info
        device_info["last_update"] = datetime.now().isoformat()
        self.device_cache[device_id] = device_info
        
        # 保存到文件
        self._save_device_cache()
        self.logger.info(f"已更新设备 {device_id} 的动作缓存（含 siid/aiid）")
    
    def _load_config(self):
        """加载配置"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                self.logger.info(f"已加载配置文件: {self.config_path}")
            else:
                # 创建默认配置
                self.config = {
                    "username": "",
                    "password": "",
                    "enableQR": True,
                    "log_level": "INFO",
                    "auto_connect": False,
                    "device_cache_ttl": 300
                }
                self._save_config()
                self.logger.info(f"已创建默认配置文件: {self.config_path}")
        except Exception as e:
            self.logger.error(f"加载配置失败: {e}")
            self.config = {}
    
    def _save_config(self):
        """保存配置"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            self.logger.info(f"配置已保存: {self.config_path}")
        except Exception as e:
            self.logger.error(f"保存配置失败: {e}")
    
    @lifecycle(id="startup")
    def startup(self, **_):
        """插件启动"""
        self.logger.info("米家插件启动中...")
        
        # 初始化适配器
        self.adapter = MijiaAdapter()
        
        # 上报状态
        self.report_status({
            "status": "initialized",
            "connected": False,
            "device_count": 0
        })
        
        # 如果配置了自动连接，尝试连接
        if self.config.get("auto_connect", False):
            asyncio.create_task(self._auto_connect())
        
        self.ctx.push_message(
            source="mijia",
            message_type="text",
            description="插件启动",
            priority=3,
            content="米家插件已启动"
        )
        
        return {"status": "started"}
    
    @lifecycle(id="shutdown")
    def shutdown(self, **_):
        """插件关闭"""
        self.logger.info("米家插件关闭中...")
        
        if self.adapter and self.connected:
            asyncio.create_task(self.adapter.disconnect())
        
        self.ctx.push_message(
            source="mijia",
            message_type="text",
            description="插件关闭",
            priority=3,
            content="米家插件已关闭"
        )
        
        return {"status": "stopped"}
    
    async def _auto_connect(self):
        """自动连接"""
        try:
            await self.connect()
        except Exception as e:
            self.logger.error(f"自动连接失败: {e}")
    
    @plugin_entry(
        id="connect",
        name="连接米家",
        description="连接到米家云服务"
    )
    async def connect(self, **_):
        """连接到米家"""
        if not self.adapter:
            return {
                "success": False,
                "error": "适配器未初始化"
            }
        
        try:
            self.logger.info("正在连接米家云服务...")
            
            # 更新状态
            self.report_status({
                "status": "connecting",
                "message": "正在连接..."
            })
            
            # 执行连接
            result = await self.adapter.connect()
            
            if result:
                self.connected = True
                self.logger.info("米家连接成功")
                
                # 推送消息
                self.ctx.push_message(
                    source="mijia",
                    message_type="text",
                    description="连接成功",
                    priority=5,
                    content="已连接到米家云服务"
                )
                
                # 更新状态
                self.report_status({
                    "status": "connected",
                    "connected": True,
                    "device_count": self.adapter.device_count
                })
                
                return {
                    "success": True,
                    "message": "连接成功"
                }
            else:
                self.logger.error("米家连接失败")
                return {
                    "success": False,
                    "error": "连接失败，请检查配置"
                }
                
        except Exception as e:
            self.logger.exception(f"连接异常: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    @plugin_entry(
        id="disconnect",
        name="断开连接",
        description="断开米家云服务连接"
    )
    async def disconnect(self, **_):
        """断开连接"""
        if not self.adapter or not self.connected:
            return {
                "success": True,
                "message": "已断开"
            }
        
        try:
            await self.adapter.disconnect()
            self.connected = False
            
            self.ctx.push_message(
                source="mijia",
                message_type="text",
                description="断开连接",
                priority=3,
                content="已断开米家云服务连接"
            )
            
            self.report_status({
                "status": "disconnected",
                "connected": False
            })
            
            return {
                "success": True,
                "message": "断开成功"
            }
            
        except Exception as e:
            self.logger.exception(f"断开连接异常: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    @plugin_entry(
        id="discover_devices",
        name="发现设备",
        description="发现米家设备",
        input_schema={
            "type": "object",
            "properties": {
                "online_only": {
                    "type": "boolean",
                    "description": "是否只返回在线设备",
                    "default": False
                },
                "force_refresh": {
                    "type": "boolean",
                    "description": "是否强制刷新（忽略缓存）",
                    "default": False
                }
            }
        }
    )
    async def discover_devices(self, online_only: bool = False, force_refresh: bool = False, **_):
        """发现设备并保存标识"""
        # 如果有缓存且不强制刷新，直接返回缓存
        if not force_refresh and self.device_cache:
            self.logger.info(f"使用缓存设备列表 ({len(self.device_cache)} 个设备)")
            device_list = list(self.device_cache.values())
            return {
                "success": True,
                "devices": device_list,
                "count": len(device_list),
                "cached": True,
                "last_discovery": self.last_discovery_time.isoformat() if self.last_discovery_time else None
            }
        
        if not self._check_connected():
            return self._not_connected_response()
        
        try:
            self.logger.info("开始发现设备...")
            
            self.report_status({
                "status": "discovering",
                "message": "正在发现设备..."
            })
            
            devices = await self.adapter.discover_devices(online_only=online_only)
            
            # 更新缓存并保存
            device_list = []
            for device in devices:
                device_info = {
                    "did": device.did,
                    "name": device.name,
                    "model": device.model,
                    "online": getattr(device, 'online', True),
                    "room_id": getattr(device, 'room_id', None),
                    "spec_type": getattr(device, 'spec_type', None),
                    "properties": {},
                    "actions": {},
                    "last_update": datetime.now().isoformat()
                }
                self.device_cache[device.did] = device_info
                device_list.append(device_info)
                
                # 异步获取设备属性（含 siid/piid）
                asyncio.create_task(self._fetch_device_details(device.did))
            
            self.last_discovery_time = datetime.now()
            
            # 保存到文件
            self._save_device_cache()
            
            self.logger.info(f"发现 {len(device_list)} 个设备，正在后台获取详细信息...")
            
            # 推送消息
            self.ctx.push_message(
                source="mijia",
                message_type="text",
                description="设备发现完成",
                priority=4,
                content=f"发现 {len(device_list)} 个米家设备，正在获取详细信息",
                metadata={"count": len(device_list)}
            )
            
            self.report_status({
                "status": "connected",
                "connected": True,
                "device_count": len(device_list)
            })
            
            return {
                "success": True,
                "devices": device_list,
                "count": len(device_list),
                "cached": False,
                "last_discovery": self.last_discovery_time.isoformat(),
                "message": "设备已发现，详细信息正在后台获取中"
            }
            
        except Exception as e:
            self.logger.exception(f"发现设备失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _fetch_device_details(self, device_id: str):
        """后台获取设备详细信息（属性、动作的 siid/piid）"""
        try:
            if not self._check_connected():
                return
            
            self.logger.info(f"正在获取设备 {device_id} 的详细信息...")
            
            # 获取设备属性
            try:
                properties = await self.adapter.get_device_properties(device_id)
                self._update_device_properties_cache(device_id, properties)
                self.logger.info(f"已获取设备 {device_id} 的 {len(properties)} 个属性")
            except Exception as e:
                self.logger.warning(f"获取设备 {device_id} 属性失败: {e}")
            
            # 获取设备动作
            try:
                actions = await self.adapter.get_device_actions(device_id)
                self._update_device_actions_cache(device_id, actions)
                self.logger.info(f"已获取设备 {device_id} 的 {len(actions)} 个动作")
            except Exception as e:
                self.logger.warning(f"获取设备 {device_id} 动作失败: {e}")
            
            # 推送完成消息
            self.ctx.push_message(
                source="mijia",
                message_type="text",
                description="设备信息获取完成",
                priority=3,
                content=f"设备 {device_id} 的详细信息已获取",
                metadata={"device_id": device_id}
            )
            
        except Exception as e:
            self.logger.error(f"获取设备 {device_id} 详细信息失败: {e}")
    
    @plugin_entry(
        id="get_devices",
        name="获取设备列表",
        description="获取已发现的设备列表"
    )
    async def get_devices(self, **_):
        """获取设备列表"""
        if not self.device_cache:
            return await self.discover_devices(force_refresh=False)
        
        return {
            "success": True,
            "devices": list(self.device_cache.values()),
            "count": len(self.device_cache),
            "cached": True,
            "last_discovery": self.last_discovery_time.isoformat() if self.last_discovery_time else None
        }
    
    @plugin_entry(
        id="get_device_by_name",
        name="按名称查找设备",
        description="根据名称查找设备标识",
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "设备名称（支持模糊匹配）"
                }
            },
            "required": ["name"]
        }
    )
    async def get_device_by_name(self, name: str, **_):
        """按名称查找设备"""
        name_lower = name.lower()
        results = []
        
        for did, device in self.device_cache.items():
            if name_lower in device.get("name", "").lower():
                results.append({
                    "did": did,
                    "name": device.get("name"),
                    "model": device.get("model"),
                    "online": device.get("online", True),
                    "properties": device.get("properties", {}),
                    "actions": device.get("actions", {})
                })
        
        return {
            "success": True,
            "devices": results,
            "count": len(results),
            "total": len(self.device_cache)
        }
    
    @plugin_entry(
        id="get_device_by_did",
        name="按ID查找设备",
        description="根据设备ID查找设备标识",
        input_schema={
            "type": "object",
            "properties": {
                "did": {
                    "type": "string",
                    "description": "设备ID"
                }
            },
            "required": ["did"]
        }
    )
    async def get_device_by_did(self, did: str, **_):
        """按设备ID查找设备"""
        device = self.device_cache.get(did)
        if not device:
            return {
                "success": False,
                "error": f"未找到设备: {did}"
            }
        
        return {
            "success": True,
            "device": device
        }
    
    @plugin_entry(
        id="control_by_name",
        name="按名称控制设备",
        description="使用设备名称控制设备（需要先发现设备）",
        input_schema={
            "type": "object",
            "properties": {
                "device_name": {
                    "type": "string",
                    "description": "设备名称"
                },
                "property_name": {
                    "type": "string",
                    "description": "属性名称（如 on, power）"
                },
                "value": {
                    "description": "要设置的值"
                }
            },
            "required": ["device_name", "property_name", "value"]
        }
    )
    async def control_by_name(self, device_name: str, property_name: str, value: Any, **_):
        """使用设备名称控制设备"""
        # 查找设备
        device_info = None
        device_id = None
        for did, info in self.device_cache.items():
            if device_name.lower() in info.get("name", "").lower():
                device_info = info
                device_id = did
                break
        
        if not device_info:
            return {
                "success": False,
                "error": f"未找到设备: {device_name}",
                "available_devices": [d.get("name") for d in self.device_cache.values()]
            }
        
        # 查找属性
        properties = device_info.get("properties", {})
        if property_name not in properties:
            return {
                "success": False,
                "error": f"设备 {device_name} 没有属性: {property_name}",
                "available_properties": list(properties.keys())
            }
        
        prop_info = properties[property_name]
        siid = prop_info.get("siid")
        piid = prop_info.get("piid")
        
        if not siid or not piid:
            # 尝试重新获取属性
            self.logger.warning(f"属性 {property_name} 缺少 siid/piid，尝试重新获取...")
            try:
                if self._check_connected():
                    new_props = await self.adapter.get_device_properties(device_id)
                    self._update_device_properties_cache(device_id, new_props)
                    # 重新获取
                    updated_device = self.device_cache.get(device_id, {})
                    updated_prop = updated_device.get("properties", {}).get(property_name, {})
                    siid = updated_prop.get("siid")
                    piid = updated_prop.get("piid")
                    if siid and piid:
                        self.logger.info(f"成功获取属性 {property_name} 的 siid={siid}, piid={piid}")
            except Exception as e:
                self.logger.error(f"重新获取属性失败: {e}")
        
        if not siid or not piid:
            return {
                "success": False,
                "error": f"属性 {property_name} 缺少标识信息 (siid/piid)，请先调用 get_device_properties 获取"
            }
        
        # 调用设置
        return await self.set_property_value(device_id, siid, piid, value)
    
    @plugin_entry(
        id="refresh_device_cache",
        name="刷新设备缓存",
        description="重新发现设备并更新缓存",
        input_schema={
            "type": "object",
            "properties": {
                "online_only": {
                    "type": "boolean",
                    "description": "是否只返回在线设备",
                    "default": False
                }
            }
        }
    )
    async def refresh_device_cache(self, online_only: bool = False, **_):
        """刷新设备缓存"""
        return await self.discover_devices(online_only=online_only, force_refresh=True)
    
    @plugin_entry(
        id="get_device_properties",
        name="获取设备属性",
        description="获取设备支持的属性列表",
        input_schema={
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "设备ID"
                }
            },
            "required": ["device_id"]
        }
    )
    async def get_device_properties(self, device_id: str, **_):
        """获取设备属性"""
        if not self._check_connected():
            return self._not_connected_response()
        
        try:
            properties = await self.adapter.get_device_properties(device_id)
            
            # 更新缓存
            self._update_device_properties_cache(device_id, properties)
            
            prop_list = []
            for prop in properties:
                prop_list.append({
                    "name": prop.name,
                    "description": prop.desc,
                    "type": prop.type,
                    "rw": prop.rw,
                    "unit": prop.unit,
                    "siid": getattr(prop, 'siid', None),
                    "piid": getattr(prop, 'piid', None),
                    "range": getattr(prop, 'range', None),
                    "value_list": getattr(prop, 'value_list', None)
                })
            
            return {
                "success": True,
                "device_id": device_id,
                "properties": prop_list,
                "count": len(prop_list)
            }
            
        except Exception as e:
            self.logger.exception(f"获取设备属性失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    @plugin_entry(
        id="get_device_actions",
        name="获取设备动作",
        description="获取设备支持的动作列表",
        input_schema={
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "设备ID"
                }
            },
            "required": ["device_id"]
        }
    )
    async def get_device_actions(self, device_id: str, **_):
        """获取设备动作"""
        if not self._check_connected():
            return self._not_connected_response()
        
        try:
            actions = await self.adapter.get_device_actions(device_id)
            
            # 更新缓存
            self._update_device_actions_cache(device_id, actions)
            
            action_list = []
            for action in actions:
                action_list.append({
                    "name": action.name,
                    "description": action.desc,
                    "siid": getattr(action, 'siid', None),
                    "aiid": getattr(action, 'aiid', None)
                })
            
            return {
                "success": True,
                "device_id": device_id,
                "actions": action_list,
                "count": len(action_list)
            }
            
        except Exception as e:
            self.logger.exception(f"获取设备动作失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    @plugin_entry(
        id="get_property_value",
        name="获取属性值",
        description="获取设备属性的当前值",
        input_schema={
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "siid": {"type": "integer"},
                "piid": {"type": "integer"}
            },
            "required": ["device_id", "siid", "piid"]
        }
    )
    async def get_property_value(self, device_id: str, siid: int, piid: int, **_):
        """获取属性值"""
        if not self._check_connected():
            return self._not_connected_response()
        
        try:
            value = await self.adapter.get_property_value(device_id, siid, piid)
            
            return {
                "success": True,
                "device_id": device_id,
                "siid": siid,
                "piid": piid,
                "value": value
            }
            
        except Exception as e:
            self.logger.exception(f"获取属性值失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    @plugin_entry(
        id="set_property_value",
        name="设置属性值",
        description="设置设备属性的值",
        input_schema={
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "siid": {"type": "integer"},
                "piid": {"type": "integer"},
                "value": {"description": "要设置的值"}
            },
            "required": ["device_id", "siid", "piid", "value"]
        }
    )
    async def set_property_value(self, device_id: str, siid: int, piid: int, value: Any, **_):
        """设置属性值"""
        if not self._check_connected():
            return self._not_connected_response()
        
        try:
            result = await self.adapter.set_property_value(device_id, siid, piid, value)
            
            if result:
                self.ctx.push_message(
                    source="mijia",
                    message_type="text",
                    description="属性设置成功",
                    priority=5,
                    content=f"设备 {device_id} 属性 {siid}:{piid} 已设置为 {value}"
                )
            
            return {
                "success": result,
                "device_id": device_id,
                "siid": siid,
                "piid": piid,
                "value": value,
                "result": result
            }
            
        except Exception as e:
            self.logger.exception(f"设置属性值失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    @plugin_entry(
        id="call_action",
        name="调用动作",
        description="调用设备动作",
        input_schema={
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "siid": {"type": "integer"},
                "aiid": {"type": "integer"},
                "params": {
                    "type": "array",
                    "description": "动作参数",
                    "default": []
                }
            },
            "required": ["device_id", "siid", "aiid"]
        }
    )
    async def call_action(self, device_id: str, siid: int, aiid: int, params: List = None, **_):
        """调用动作"""
        if not self._check_connected():
            return self._not_connected_response()
        
        if params is None:
            params = []
        
        try:
            result = await self.adapter.call_action(device_id, siid, aiid, params)
            
            self.ctx.push_message(
                source="mijia",
                message_type="text",
                description="动作调用成功",
                priority=5,
                content=f"设备 {device_id} 动作 {siid}:{aiid} 已执行"
            )
            
            return {
                "success": True,
                "device_id": device_id,
                "siid": siid,
                "aiid": aiid,
                "params": params,
                "result": result
            }
            
        except Exception as e:
            self.logger.exception(f"调用动作失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    @plugin_entry(
        id="search_devices",
        name="搜索设备",
        description="搜索和过滤设备",
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词（设备名或型号）",
                    "default": ""
                },
                "online_only": {
                    "type": "boolean",
                    "description": "是否只显示在线设备",
                    "default": False
                }
            }
        }
    )
    async def search_devices(self, query: str = "", online_only: bool = False, **_):
        """搜索设备"""
        if not self.device_cache:
            await self.discover_devices(force_refresh=False)
        
        results = []
        query_lower = query.lower() if query else ""
        
        for device in self.device_cache.values():
            # 关键词过滤
            if query and query_lower not in device["name"].lower() and query_lower not in device["model"].lower():
                continue
            
            # 在线状态过滤
            if online_only and not device.get("online", True):
                continue
            
            results.append(device)
        
        return {
            "success": True,
            "query": query,
            "online_only": online_only,
            "devices": results,
            "count": len(results),
            "total": len(self.device_cache)
        }
    
    @plugin_entry(
        id="get_status",
        name="获取状态",
        description="获取插件状态"
    )
    async def get_status(self, **_):
        """获取插件状态"""
        return {
            "success": True,
            "connected": self.connected,
            "device_count": len(self.device_cache),
            "last_discovery": self.last_discovery_time.isoformat() if self.last_discovery_time else None,
            "config": {
                "username": self.config.get("username", "")[:3] + "***" if self.config.get("username") else "",
                "enableQR": self.config.get("enableQR", True),
                "auto_connect": self.config.get("auto_connect", False)
            }
        }
    
    @plugin_entry(
        id="update_config",
        name="更新配置",
        description="更新插件配置",
        input_schema={
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
                "enableQR": {"type": "boolean"},
                "auto_connect": {"type": "boolean"}
            }
        }
    )
    async def update_config(self, **kwargs):
        """更新配置"""
        updated = False
        
        for key, value in kwargs.items():
            if key in self.config and value is not None:
                self.config[key] = value
                updated = True
        
        if updated:
            self._save_config()
            
            self.ctx.push_message(
                source="mijia",
                message_type="text",
                description="配置已更新",
                priority=4,
                content="米家插件配置已更新"
            )
        
        return {
            "success": True,
            "updated": updated,
            "config": {k: v for k, v in self.config.items() if k != "password"}
        }
    
    @timer_interval(
        id="heartbeat",
        seconds=60,
        name="心跳",
        description="定期检查连接状态",
        auto_start=True
    )
    async def heartbeat(self, **_):
        """心跳任务"""
        if self.connected and self.adapter:
            # 检查连接状态
            try:
                # 简单的连接检查
                if hasattr(self.adapter, 'connected') and not self.adapter.connected:
                    self.connected = False
                    self.logger.warning("检测到连接已断开")
                    
                    self.ctx.push_message(
                        source="mijia",
                        message_type="text",
                        description="连接断开",
                        priority=7,
                        content="米家连接已断开"
                    )
                    
                    self.report_status({
                        "status": "disconnected",
                        "connected": False
                    })
            except Exception as e:
                self.logger.error(f"心跳检查失败: {e}")
        
        return {"checked": True}
    
    def _check_connected(self) -> bool:
        """检查是否已连接"""
        if not self.connected or not self.adapter:
            return False
        return True
    
    def _not_connected_response(self) -> Dict:
        """返回未连接的响应"""
        return {
            "success": False,
            "error": "未连接到米家云服务，请先调用 connect"
        }
