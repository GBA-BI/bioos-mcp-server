"""
Dockstore 搜索功能测试脚本
用于测试与 bioos_mcp_server.py 中相同的搜索功能
"""

import asyncio
import sys
import time
import traceback
from typing import Dict, Any, List, Optional
sys.path.append("/mnt/d/Project/MCP/bioos-mcp-server/src")

from bioos_mcp.tools.dockstore_search import DockstoreSearch

# 模拟 DockstoreSearchConfig 对象
class MockConfig:
    def __init__(self, query, query_type="match_phrase", sentence=False, output_full=False):
        self.query = query
        self.query_type = query_type
        self.sentence = sentence
        self.output_full = output_full

async def test_search():
    """测试 Dockstore 搜索功能"""
    try:
        print("创建测试配置...")
        
        # 模拟用户查询参数 - 肺癌WGS变异检测
        test_config = MockConfig(
            query=[
                ["description", "AND", "SNP CNV workflow WGS variant calling"],
                ["description", "OR", "tumor normal paired somatic variant"],
                ["description", "OR", "lung cancer genomic analysis"]
            ],
            query_type="match_phrase",
            sentence=True,
            output_full=True
        )
        
        print(f"创建测试配置完成: {test_config.__dict__}")
        
        # 创建客户端
        print("初始化 DockstoreSearch 客户端...")
        client = DockstoreSearch()
        
        # 处理查询参数格式 - 与 bioos_mcp_server.py 相同的处理逻辑
        queries = []
        for query_item in test_config.query:
            if len(query_item) == 3:
                field, operator, term = query_item
                print("...operator....",operator)
                queries.append({
                    "terms": [term],
                    "fields": [field],
                    "operator": operator.upper() if operator in ["AND", "OR"] else "AND"
                })
                print(f"添加查询: field={field}, operator={operator}, term={term}")
            else:
                print(f"跳过无效的查询项: {query_item}")
        
        if not queries:
            print("没有有效的查询条件")
            return False
            
        # 添加超时处理
        print(f"开始执行搜索，参数: queries={queries}, sentence={test_config.sentence}, query_type={test_config.query_type}")
        print("设置超时时间: 60秒")
        
        start_time = time.time()
        try:
            results = await asyncio.wait_for(
                client.search(queries, test_config.sentence, test_config.query_type),
                timeout=60
            )
            end_time = time.time()
            print(f"搜索完成，耗时: {end_time - start_time:.2f}秒")
        except asyncio.TimeoutError:
            print("搜索操作超时(60秒)")
            return False
        
        if not results:
            print("搜索未返回结果")
            return False
            
        if isinstance(results, dict) and "error" in results:
            print(f"搜索错误: {results['error']}")
            return False
            
        if "hits" not in results:
            print("未找到匹配的工作流")
            return False
            
        # 输出结果统计
        hits = results.get("hits", {})
        total = hits.get("total", {}).get("value", 0)
        print(f"搜索成功，找到 {total} 个匹配的工作流")
        
        # 打印前5个结果
        for i, hit in enumerate(hits.get("hits", [])[:5]):
            source = hit.get("_source", {})
            print(f"\n结果 {i+1}:")
            print(f"  名称: {source.get('workflowName', 'Unknown')}")
            print(f"  路径: {source.get('full_workflow_path', 'Unknown')}")
            print(f"  描述: {source.get('description', 'No description')[:100]}...")
            
        # 格式化结果
        if hasattr(client, "format_results"):
            print("\n格式化结果测试:")
            try:
                formatted = client.format_results(results, test_config.output_full)
                print(f"格式化完成，结果长度: {len(formatted)}")
            except Exception as e:
                print(f"格式化结果时出错: {str(e)}")
        
        return True
    except Exception as e:
        print(f"测试过程中发生异常: {type(e).__name__}: {str(e)}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("开始Dockstore搜索测试")
    
    try:
        asyncio.run(test_search())
    except KeyboardInterrupt:
        print("\n测试被用户中断")
    except Exception as e:
        print(f"运行测试时出错: {str(e)}")
        traceback.print_exc()
    
    print("\n测试完成")