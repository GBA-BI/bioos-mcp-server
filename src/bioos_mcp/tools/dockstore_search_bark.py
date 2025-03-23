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
- Automatic file downloads

Searchable Fields:
- full_workflow_path: Complete workflow path
- description: Workflow description
- name: Workflow name
- organization: Organization name
- labels: Workflow labels
- workflowVersions.sourceFiles.content: Workflow source file content

Usage Examples:
1. Search for single-cell RNA analysis workflows:
   python dockstore_search.py -q "single cell RNA" "description" "AND" --sentence

2. Search and download workflow:
   python dockstore_search.py -d "github.com/broadinstitute/TAG-public/CNV-Profiler" "full_workflow_path" "AND"
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
    
    API_BASE = "https://dockstore.org/api/api/ga4gh/v2/extended/tools/entry/_search"
    API_TOOLS = "https://dockstore.org/api/ga4gh/v2/tools"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    def __init__(self) -> None:
        """Initialize the DockstoreSearch client."""
        self.base_url = "https://dockstore.org/api/workflows"
        self.search_url = self.API_BASE
        self.headers = {
            "accept": "application/json",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "origin": "https://dockstore.org",
            "priority": "u=1, i",
            "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": self.USER_AGENT,
            "x-dockstore-ui": "2.13.3",
            "x-request-id": str(uuid4()),
            "x-session-id": str(uuid4())
        }

    def _build_search_body(
        self, 
        queries: List[Dict[str, Union[List[str], str]]], 
        is_sentence: bool,
        query_type: str
    ) -> Dict[str, Any]:
        """Build the search request body."""
        search_body = {
            "size": 201,
            "_source": [
                "all_authors", "approvedAITopic", "descriptorType",
                "descriptorTypeSubclass", "full_workflow_path", "gitUrl",
                "name", "namespace", "organization", "private_access",
                "providerUrl", "repository", "starredUsers", "toolname",
                "tool_path", "topicAutomatic", "topicSelection", "verified",
                "workflowName", "description", "workflowVersions"
            ],
            "sort": [
                {"archived": {"order": "asc"}},
                {"_score": {"order": "desc"}}
            ],
            "highlight": {
                "type": "unified",
                "pre_tags": ["<b>"],
                "post_tags": ["</b>"],
                "fields": {
                    "full_workflow_path": {},
                    "tool_path": {},
                    "workflowVersions.sourceFiles.content": {},
                    "tags.sourceFiles.content": {},
                    "description": {},
                    "labels": {},
                    "all_authors.name": {},
                    "topicAutomatic": {},
                    "categories.topic": {},
                    "categories.displayName": {}
                }
            },
            "query": {
                "bool": {
                    "must": [{"match": {"_index": "workflows"}}],
                    "should": [],
                    "minimum_should_match": 1
                }
            }
        }

        # Process query conditions
        for query in queries:
            terms = query.get("terms", [])
            fields = query.get("fields", [])
            
            for term, field in zip(terms, fields):
                if query_type == "wildcard":
                    search_body["query"]["bool"]["should"].append({
                        "wildcard": {
                            field: {
                                "value": f"*{term}*",
                                "case_insensitive": True,
                                "boost": 14 if field in ["full_workflow_path", "tool_path"] else 2
                            }
                        }
                    })
                else:
                    search_body["query"]["bool"]["should"].append({
                        "match": {
                            field: {
                                "query": term,
                                "boost": 2
                            }
                        }
                    })
        
        return search_body

    # 修改 dockstore_search.py 中的 search 方法
    async def search(
        self, 
        queries: List[Dict[str, Union[List[str], str]]], 
        is_sentence: bool = False,
        query_type: str = "match_phrase"
    ) -> Optional[Dict[str, Any]]:
        """Execute workflow search."""
        try:
            print(f"开始构建搜索查询: {queries}")
            search_body = self._build_search_body(queries, is_sentence, query_type)
            print(f"搜索体构建完成, 准备发送请求")
            
            async with httpx.AsyncClient(timeout=30.0) as client:  # 设置30秒超时
                print(f"正在发送请求到 {self.search_url}")
                response = await client.post(
                    self.search_url,
                    headers=self.headers,
                    json=search_body
                )
                print(f"请求完成, 状态码: {response.status_code}")
                
                if response.status_code != 200:
                    print(f"错误响应: {response.text}")
                    return None
                    
                return response.json()
        except httpx.TimeoutException:
            print("请求超时")
            return {"error": "Request timed out after 30 seconds"}
        except Exception as e:
            print(f"搜索过程中发生错误: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def format_results(self, results: dict) -> str:
        """Format search results as a concise list of links."""
        if not results or "hits" not in results:
            return "No matching workflows found"
        
        formatted = ["The following workflows were found in Dockstore:\n"]
        workflows = []
        
        for hit in results["hits"].get("hits", []):
            source = hit.get("_source", {})
            score = hit.get("_score", 0)
            
            name = (source.get('workflowName') or 
                   source.get('name') or 
                   source.get('repository') or 
                   'Unnamed Workflow')
            path = source.get('full_workflow_path', '')
            desc = source.get('description', '')
            if desc:
                desc = desc.split('\n')[0]
            
            workflows.append({
                'name': name,
                'path': path,
                'desc': desc,
                'score': score
            })
        
        workflows.sort(key=lambda x: x['score'], reverse=True)
        total_results = len(workflows)
        display_count = min(total_results, 5)
        
        if total_results > 5:
            formatted.append(f"Found {total_results} workflows, showing top 5 by relevance:\n")
        else:
            formatted.append(f"Found {total_results} workflow(s):\n")
        
        for wf in workflows[:display_count]:
            url = f"https://dockstore.org/workflows/{wf['path']}"
            formatted.append(f"- [{wf['name']}]({url}) (similarity: {wf['score']:.2f})")
            if wf['desc']:
                formatted.append(f"  {wf['desc']}\n")
        
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
    
    args = parser.parse_args()
    client = DockstoreSearch()
    
    try:
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
            print("请使用 -q 选项指定搜索条件")
            return
            
        # 执行搜索
        results = await client.search(queries, args.sentence)
        if not results or "hits" not in results or not results["hits"].get("hits"):
            print("未找到相关工作流")
            return
            
        # 显示搜索结果
        print(client.format_results(results, args.outputfull))
        
        # 保存搜索结果
        result_path = os.path.abspath('dockstore_results.json')
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        #print(f"\n结果文件已保存到: {result_path}")
            
    except Exception as e:
        print(f"执行出错: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())