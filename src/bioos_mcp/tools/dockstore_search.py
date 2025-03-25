"""Dockstore Workflow Search and Download Tool

This tool provides two main functionalities:
1. Search for workflows on Dockstore
2. Download WDL files from specified workflows

Features:
- Support complex multi-field searches
- Support AND/OR boolean operations
- Support wildcard matching
- Support full sentence search
- Sort results by relevance
- Filter by descriptor type, verification status and more

Searchable Fields:
- full_workflow_path: Complete workflow path
- description: Workflow description
- name: Workflow name
- workflowName: Workflow display name
- organization: Organization name
- all_authors.name: Author names
- labels.value: Workflow labels
- categories.name: Workflow categories
- workflowVersions.sourceFiles.content: Workflow source file content
- input_file_formats.value: Input file formats
- output_file_formats.value: Output file formats

Usage Examples:
1. Basic search for workflows about RNA sequencing:
   python dockstore_search.py -q "RNA-seq" "description" "AND"

2. Search for WDL workflows for variant calling:
   python dockstore_search.py -q "variant calling" "description" "AND" --descriptor-type "WDL"

3. Search for verified workflows for cancer analysis:
   python dockstore_search.py -q "cancer" "description" "AND" --verified-only

4. Multi-field search with different criteria:
   python3 dockstore_search.py -q "broadinstitute" "organization" "AND" -q "WDL" "descriptorType" "AND"

5. Search with wildcard matching:
   python dockstore_search.py -q "genom*" "description" "OR" --type wildcard

6. Search for workflows by author:
   python dockstore_search.py -q "John Smith" "all_authors.name" "AND"

7. Search for workflows with specific input format:
   python dockstore_search.py -q "BAM" "input_file_formats.value" "AND"

8. Search for workflows with specific output format:
   python dockstore_search.py -q "VCF" "output_file_formats.value" "AND"

9. Search for workflows with full detail output:
   python dockstore_search.py -q "exome" "description" "AND" --outputfull

10. Search for specific workflow by path:
    python dockstore_search.py -q "github.com/broadinstitute/gatk/Mutect2" "full_workflow_path" "AND"

11. Search for workflows in specific category:
    python dockstore_search.py -q "Genomics" "categories.name" "AND"

12. Search for both active and archived workflows:
    python dockstore_search.py -q "legacy" "description" "AND" --include-archived
"""

from typing import Any, Dict, List, Optional, Union
from pathlib import Path
from uuid import uuid4
import argparse
import asyncio
import httpx
import json
import os


class DockstoreSearch:
    """Dockstore search client for querying workflows using Elasticsearch."""
    
    API_BASE = "https://dockstore.miracle.ac.cn/api/api/ga4gh/v2/extended/tools/entry/_search"
    API_TOOLS = "https://dockstore.miracle.ac.cn/api/ga4gh/v2/tools"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    def __init__(self) -> None:
        """Initialize the DockstoreSearch client."""
        self.base_url = "https://dockstore.miracle.ac.cn/api/workflows"
        self.search_url = self.API_BASE
        self.headers = {
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "Content-Type": "text/plain",  # 关键修改：使用 text/plain
            "Cookie": "ory_kratos_session=MTc0Mjc4NTAyMHxKMDE3d2VzUVhhRlpVQmcxUDNtTEZGTnNZOU5CT3R6SDNsc25rM2VOYmU2cG9WMGRLcjFpMTY5d25Rd0wxUGplaXZTZE1mN2l6M0ZkRGdoeDA1STB5Q1RiMm5Bak95bHJiZHB0MlVsYjBxNjhQRUJFbzBnU0owOExFSlFhdGp1N0E4bGJQWUR5UWR2bzhXQ3BVOS1KSjdmY05adk5XcHhLeHJrNmdoeTRlNnA4Q214WFRrOURCaUFFeHJ4a29oVlFWZVY2ZWJ3Yk91N1k5SS1iNU91ZEFlSWtyWlJFWWJCLXRLMXNhRU5xV3RVWGlROGRRVUJDLXlfd0RYbEdraTZrRm9kVkkyRT188Jy1Xnkj4Yj5FJeDzpHxLW3TnpRMaUxol_G0nY-dtNM=",  # 添加 cookie
            "Origin": "https://dockstore.miracle.ac.cn",
            "Referer": "https://dockstore.miracle.ac.cn/search?descriptorType=WDL&entryType=workflows&searchMode=files",  # 更新 referer
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": self.USER_AGENT,
            "X-Dockstore-UI": "",
            "X-Request-ID": str(uuid4()),
            "X-Session-ID": str(uuid4()),
            "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"'
        }

    def get_direct_search_body(self, descriptor_type=None) -> Dict[str, Any]:
        """构建精确匹配curl请求的搜索体。"""
        return {
            "size": 201,
            "_source": [
                "author", "descriptorType", "full_workflow_path", "gitUrl", 
                "name", "namespace", "organization", "private_access", 
                "providerUrl", "repository", "starredUsers", "toolname", 
                "tool_path", "topicAutomatic", "verified", "workflowName",
                "description", "categories"
            ],
            "query": {
                "bool": {
                    "filter": {"term": {"descriptorType": descriptor_type or "WDL"}},
                    "must": [
                        {"match": {"_index": "workflows"}},
                        {"match_all": {}}
                    ]
                }
            }
        }

    def _build_search_body(
        self, 
        queries: List[Dict[str, Union[List[str], str]]], 
        is_sentence: bool,
        query_type: str,
        descriptor_type: str = None,
        verified_only: bool = False,
        include_archived: bool = False
    ) -> Dict[str, Any]:
        """Build the search request body with minimal structure to match curl command."""
        # 从最新的 curl 命令直接模仿请求体结构
        search_body = {
            "size": 201,
            "_source": [
                "author", "descriptorType", "full_workflow_path", "gitUrl", 
                "name", "namespace", "organization", "private_access", 
                "providerUrl", "repository", "starredUsers", "toolname", 
                "tool_path", "topicAutomatic", "verified", "workflowName",
                "description", "categories"
            ],
            "query": {
                "bool": {
                    "must": [
                        {"match": {"_index": "workflows"}},
                        {"match_all": {}}
                    ]
                }
            }
        }

        # 如果指定了描述符类型，添加过滤器
        if descriptor_type:
            search_body["query"]["bool"]["filter"] = {
                "term": {"descriptorType": descriptor_type}
            }
        
        # 处理查询条件
        if queries and len(queries) > 0:
            term = queries[0].get("terms", [""])[0]
            field = queries[0].get("fields", [""])[0]
            
            # 只有当实际有查询条件时才添加搜索字段
            if term and field and term != "*":
                if field == "descriptorType":
                    # 如果字段是 descriptorType，直接使用 term 过滤
                    search_body["query"]["bool"]["filter"] = {
                        "term": {"descriptorType": term}
                    }
                else:
                    # 对于其他字段，使用适当的查询类型
                    if query_type == "wildcard":
                        if "should" not in search_body["query"]["bool"]:
                            search_body["query"]["bool"]["should"] = []
                            search_body["query"]["bool"]["minimum_should_match"] = 1
                            
                        search_body["query"]["bool"]["should"].append({
                            "wildcard": {
                                field: {
                                    "value": f"*{term}*",
                                    "case_insensitive": True
                                }
                            }
                        })
                    else:
                        if "should" not in search_body["query"]["bool"]:
                            search_body["query"]["bool"]["should"] = []
                            search_body["query"]["bool"]["minimum_should_match"] = 1
                            
                        match_type = "match_phrase" if is_sentence else "match"
                        search_body["query"]["bool"]["should"].append({
                            match_type: {
                                field: {"query": term}
                            }
                        })
        
        return search_body

    async def direct_search(self, descriptor_type=None) -> Optional[Dict[str, Any]]:
        """直接使用与curl命令完全相同的请求结构。"""
        try:
            print(f"使用直接搜索方法查找 {descriptor_type or 'WDL'} 工作流")
            search_body = self.get_direct_search_body(descriptor_type)
            
            # 调试输出
            request_body_str = json.dumps(search_body)
            print(f"请求体: {request_body_str}")
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                print(f"正在发送请求到 {self.search_url}")
                response = await client.post(
                    self.search_url,
                    headers=self.headers,
                    content=request_body_str  # 使用 content 字符串
                )
                print(f"请求完成, 状态码: {response.status_code}")
                
                if response.status_code != 200:
                    print(f"错误响应: {response.text}")
                    return None
                    
                return response.json()
        except Exception as e:
            print(f"直接搜索过程中发生错误: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    async def search(
        self, 
        queries: List[Dict[str, Union[List[str], str]]], 
        is_sentence: bool = False,
        query_type: str = "match_phrase",
        descriptor_type: str = None,
        verified_only: bool = False,
        include_archived: bool = False
    ) -> Optional[Dict[str, Any]] :
        """Execute workflow search with minimal request body."""
        try:
            print(f"开始构建搜索查询: {queries}")
            search_body = self._build_search_body(
                queries, 
                is_sentence, 
                query_type,
                descriptor_type,
                verified_only,
                include_archived
            )
            print(f"搜索体构建完成, 准备发送请求")
            
            # 调试输出
            request_body_str = json.dumps(search_body)
            print(f"请求体: {request_body_str}")
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                print(f"正在发送请求到 {self.search_url}")
                response = await client.post(
                    self.search_url,
                    headers=self.headers,
                    content=request_body_str  # 使用 content 字符串
                )
                print(f"请求完成, 状态码: {response.status_code}")
                
                if response.status_code != 200:
                    print(f"错误响应: {response.text}")
                    return None
                    
                result = response.json()
                
                # 检查结果是否有效
                if not result or not isinstance(result, dict):
                    print(f"返回了无效的结果格式: {result}")
                    return None
                    
                # 检查hits是否存在，以及是否包含任何结果
                if "hits" not in result or not result["hits"] or not result["hits"].get("hits"):
                    print(f"查询 '{queries}' 没有找到匹配结果")
                    # 返回空结果结构而不是None，这样可以在后续处理中正确识别为"没有结果"
                    return {"hits": {"total": {"value": 0}, "hits": []}}
                    
                # 打印结果计数
                hits_count = len(result["hits"].get("hits", []))
                print(f"查询返回了 {hits_count} 个结果")
                
                return result
        except Exception as e:
            print(f"搜索过程中发生错误: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def format_results(self, results: dict, output_full: bool = False) -> Union[str, List[str]] :
        """Format search results as a concise list of links with enhanced information."""
        # 检查结果是否为空或无效
        if not results or "hits" not in results:
            return "未找到相关工作流"
            
        # 检查是否有搜索命中
        hits = results["hits"].get("hits", [])
        if not hits:
            return "未找到相关工作流"
        
        formatted = ["在 Dockstore 中找到以下工作流:\n"]
        workflows = []
        
        for hit in hits:
            source = hit.get("_source", {})
            score = hit.get("_score", 0)
            
            name = (source.get('workflowName') or 
                   source.get('name') or 
                   source.get('repository') or 
                   '未命名工作流')
            path = source.get('full_workflow_path', '')
            desc = source.get('description', '')
            if desc:
                desc = desc.split('\n')[0]
                
            # 增强信息
            workflow_info = {
                'name': name,
                'path': path,
                'desc': desc,
                'score': score,
                'descriptor_type': source.get('descriptorType', ''),
                'categories': [cat.get('name', '') for cat in source.get('categories', [])] if source.get('categories') else [],
                'verified': source.get('verified', False),
                'authors': [author.get('name', '') for author in source.get('all_authors', [])] if source.get('all_authors') else [],
                'organization': source.get('organization', ''),
                'input_formats': [fmt.get('value', '') for fmt in source.get('input_file_formats', [])] if source.get('input_file_formats') else [],
                'output_formats': [fmt.get('value', '') for fmt in source.get('output_file_formats', [])] if source.get('output_file_formats') else []
            }
            
            workflows.append(workflow_info)
        
        # 检查是否实际添加了任何工作流
        if not workflows:
            return "未找到相关工作流"
            
        workflows.sort(key=lambda x: x['score'], reverse=True)
        total_results = len(workflows)
        display_count = min(total_results, 5)
        
        if total_results > 5:
            formatted.append(f"找到 {total_results} 个工作流, 显示前 {display_count} 个相关结果:\n")
        else:
            formatted.append(f"找到 {total_results} 个工作流:\n")
        
        for wf in workflows[:display_count]:
            url = f"https://dockstore.miracle.ac.cn/workflows/{wf['path']}"
            #base_info = f"- [{wf['name']}]({url}) (相似度: {wf['score']:.2f})"
            base_info = f"- [{wf['name']}]({url})"
            #if wf['verified']:
            #    base_info += " ✓"  # 添加验证标记
                
            formatted.append(base_info)
                
            if output_full:
                if wf['descriptor_type']:
                    formatted.append(f"  类型: {wf['descriptor_type']}")
                if wf['categories']:
                    formatted.append(f"  分类: {', '.join(wf['categories'])}")
                if wf['authors']:
                    formatted.append(f"  作者: {', '.join(wf['authors'])}")
                if wf['organization']:
                    formatted.append(f"  组织: {wf['organization']}")
                if wf['input_formats']:
                    formatted.append(f"  输入格式: {', '.join(wf['input_formats'])}")
                if wf['output_formats']:
                    formatted.append(f"  输出格式: {', '.join(wf['output_formats'])}")
                    
            formatted.append("")  # 添加空行分隔
        
        if output_full:
            return formatted
        else:
            return "\n".join(formatted)

async def main():
    """Dockstore 工作流搜索工具
    
    用法:
    1. 多条件搜索:
       python dockstore_search.py -q "term1" "field1" "operator1" -q "term2" "field2" "operator2"
    """
    parser = argparse.ArgumentParser(description='Dockstore 工作流搜索工具')
    
    # 查询参数
    parser.add_argument('-q', '--query', 
                       action='append', 
                       nargs=3,
                       metavar=('TERM', 'FIELD', 'OPERATOR'),
                       help='查询参数：搜索词 搜索字段 布尔操作符(AND/OR), 可多次使用')
    
    # 可选参数
    parser.add_argument('-t', '--type',
                       choices=['match_phrase', 'wildcard'],
                       default='match_phrase',
                       help='查询类型: match_phrase (默认) 或 wildcard')
    parser.add_argument('--sentence',
                       action='store_true',
                       help='将搜索词作为完整句子处理')
    parser.add_argument('--outputfull',
                       action='store_true',
                       help='显示完整工作流信息')
    parser.add_argument('--descriptor-type',
                       choices=['WDL', 'CWL', 'NFL'],
                       help='只返回指定描述符类型的工作流')
    parser.add_argument('--verified-only',
                       action='store_true',
                       help='只返回已验证的工作流')
    parser.add_argument('--include-archived',
                       action='store_true',
                       help='包含已归档的工作流')
    parser.add_argument('--direct-search',
                       action='store_true',
                       help='使用直接搜索方法（适用于普通搜索失败的情况）')
    
    args = parser.parse_args()
    client = DockstoreSearch()
    
    try:
        # 使用直接搜索选项
        if args.direct_search:
            results = await client.direct_search(args.descriptor_type)
            if results and "hits" in results and results["hits"].get("hits"):
                print(client.format_results(results, args.outputfull))
                
                # 保存搜索结果
                result_path = os.path.abspath('dockstore_results.json')
                with open(result_path, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
            else:
                print("直接搜索未找到相关工作流")
            return
        
        # 从多个 -q 参数构建查询
        queries = []
        if args.query:
            for term, field, operator in args.query:
                queries.append({
                    "terms": [term],
                    "fields": [field],
                    "operator": operator.upper(),
                    "query_type": args.type
                })
        
        if not queries:
            print("请使用 -q 选项指定搜索条件，或添加 --direct-search 选项")
            return
            
        # 执行搜索
        results = await client.search(
            queries, 
            args.sentence, 
            args.type,
            args.descriptor_type,
            args.verified_only,
            args.include_archived
        )
        
        # 检查结果是否包含实际命中
        if (not results or 
            "hits" not in results or 
            not results["hits"].get("hits", [])):
            # 移除尝试直接搜索的代码，直接显示未找到结果的消息
            print("未找到相关工作流")
            return
        
        # 显示搜索结果
        formatted_results = client.format_results(results, args.outputfull)
        print(formatted_results)
        
        # 只有在真正找到结果时才保存
        if formatted_results != "未找到相关工作流":
            # 保存搜索结果
            result_path = os.path.abspath('dockstore_results.json')
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
        
    except Exception as e:
        print(f"执行出错: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())