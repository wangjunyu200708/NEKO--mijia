#!/usr/bin/env python3
"""米家插件测试程序"""

import asyncio
import json
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from plugin.plugins.mijia import MijiaPlugin
from plugin.sdk.context import PluginContext


class MockContext:
    """模拟的插件上下文"""
    
    def __init__(self):
        self.plugin_id = "mijia"
        self.config_path = Path("config/mijia.json")
        self.logger = self
        self.status_queue = []
        self.message_queue = []
    
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
        print(f"[STATUS] {json.dumps(status, ensure_ascii=False)}")
        self.status_queue.append(status)
    
    def push_message(self, **kwargs):
        print(f"[MESSAGE] {json.dumps(kwargs, ensure_ascii=False)}")
        self.message_queue.append(kwargs)


async def run_tests():
    """运行测试"""
    print("=" * 50)
    print("米家插件测试程序")
    print("=" * 50)
    
    # 创建模拟上下文
    ctx = MockContext()
    
    # 创建插件实例
    print("\n1. 初始化插件...")
    plugin = MijiaPlugin(ctx)
    print("✓ 插件初始化完成")
    
    # 启动插件
    print("\n2. 启动插件...")
    result = plugin.startup()
    print(f"✓ 启动结果: {result}")
    
    # 测试连接（需要用户输入配置）
    print("\n3. 测试连接...")
    print("请确保已在 config/mijia.json 中配置了用户名密码")
    
    response = input("是否继续连接测试? (y/n): ")
    if response.lower() == 'y':
        result = await plugin.connect()
        print(f"连接结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
        
        if result.get("success"):
            # 发现设备
            print("\n4. 发现设备...")
            devices_result = await plugin.discover_devices()
            print(f"发现结果: {json.dumps(devices_result, ensure_ascii=False, indent=2)}")
            
            # 获取设备列表
            print("\n5. 获取设备列表...")
            devices = await plugin.get_devices()
            print(f"设备列表: {json.dumps(devices, ensure_ascii=False, indent=2)}")
            
            # 如果有设备，测试获取属性
            if devices.get("devices") and len(devices["devices"]) > 0:
                first_device = devices["devices"][0]
                device_id = first_device["did"]
                
                print(f"\n6. 测试第一个设备: {first_device['name']} ({device_id})")
                
                # 获取设备属性
                props_result = await plugin.get_device_properties(device_id)
                print(f"设备属性: {json.dumps(props_result, ensure_ascii=False, indent=2)}")
                
                # 搜索设备测试
                print("\n7. 搜索设备测试...")
                search_result = await plugin.search_devices(query=first_device["name"][:2])
                print(f"搜索结果: {json.dumps(search_result, ensure_ascii=False, indent=2)}")
            
            # 获取状态
            print("\n8. 获取插件状态...")
            status = await plugin.get_status()
            print(f"插件状态: {json.dumps(status, ensure_ascii=False, indent=2)}")
            
            # 断开连接
            print("\n9. 断开连接...")
            disconnect_result = await plugin.disconnect()
            print(f"断开结果: {disconnect_result}")
    
    # 关闭插件
    print("\n10. 关闭插件...")
    shutdown_result = plugin.shutdown()
    print(f"关闭结果: {shutdown_result}")
    
    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)


def main():
    """主函数"""
    asyncio.run(run_tests())


if __name__ == "__main__":
    main()