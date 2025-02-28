"""
Dockstore Workflow Search Tool

This script provides a powerful interface to search for workflows in Dockstore using Elasticsearch queries.
It supports complex boolean searches across multiple fields with different matching strategies.

Features:
- Boolean search (AND/OR operations)
- Multiple field search
- Wildcard and phrase matching
- Result highlighting
- Formatted output
- JSON result export

Available Search Fields:
- full_workflow_path: Full path of the workflow
- tool_path: Path of the tool
- description: Workflow description
- name: Workflow name
- all_authors.name: Author names
- organization: Organization name
- labels: Workflow labels
- topicAutomatic: Automatic topics
- categories.topic: Category topics
- categories.displayName: Category display names
- workflowVersions.sourceFiles.content: Content of workflow source files
- tags.sourceFiles.content: Content of tag source files

Usage Examples:
1. Simple search:
   python dockstore_search.py -q "cnv" "description" "AND"

2. Multiple field search with AND:
   python dockstore_search.py -q "cnv" "description" "AND" -q "workflow" "name" "AND"

3. Multiple field search with OR:
   python dockstore_search.py -q "cnv" "description" "OR" -q "variant" "name" "OR"

4. Mixed boolean search:
   python dockstore_search.py -q "cnv" "description" "AND" -q "variant" "name" "OR"

5. Wildcard search:
   python dockstore_search.py -q "cnv" "description" "AND" -t wildcard

6. Sentence search:
   python dockstore_search.py -q "copy number variation analysis" "description" "AND" --sentence

Arguments:
  -q, --query TERM FIELD OPERATOR  Search parameters (can be used multiple times):
                                  - TERM: Search term
                                  - FIELD: Field to search in
                                  - OPERATOR: Boolean operator (AND/OR)
  -t, --type {match_phrase,wildcard}
                                  Query type:
                                  - match_phrase: Exact phrase matching (default)
                                  - wildcard: Pattern matching with * wildcards
  --outputfull                    Display full workflow information
  --sentence                      Treat search term as a complete sentence
  --get-files                     Get workflow files for a specific workflow path

Output:
- Formatted console output with workflow details
- JSON file (dockstore_results.json) with complete search results

Note: Results are sorted by:
1. Non-archived workflows first
2. Star count (descending)
"""

from typing import Any, Optional, List, Dict, Union
import httpx
import json
import asyncio
import argparse
from uuid import uuid4
import os

class DockstoreSearch:
    """Dockstore search client for querying workflows using Elasticsearch."""
    
    # 更新 API 端点
    API_BASE = "https://dockstore.org/api/api/ga4gh/v2/extended/tools/entry/_search"
    API_TOOLS = "https://dockstore.org/api/ga4gh/v2/tools"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

    def __init__(self):
        self.base_url = "https://dockstore.org/api/workflows"
        self.search_url = self.API_BASE
        self.headers = {
            "accept": "application/json",
            "accept-language": "zh-CN,zh;q=0.9",
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

    def _build_search_body(self, 
                          queries: List[Dict[str, Union[List[str], str]]], 
                          is_sentence: bool,
                          query_type: str) -> Dict[str, Any]:
        """构建搜索请求体"""
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
                    "must": {"match": {"_index": "workflows"}},
                    "should": [],
                    "minimum_should_match": 1
                }
            }
        }

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

    async def search(self, 
                    queries: List[Dict[str, Union[List[str], str]]], 
                    is_sentence: bool = False,
                    query_type: str = "match_phrase") -> Optional[Dict[str, Any]]:
        """执行工作流搜索"""
        search_body = self._build_search_body(queries, is_sentence, query_type)
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.search_url,
                    json=search_body,
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                print(f"搜索请求失败: {str(e)}")
                if isinstance(e, httpx.HTTPError) and hasattr(e, 'response'):
                    print(f"响应状态码: {e.response.status_code}")
                    print(f"响应内容: {e.response.text}")
                return None

    @staticmethod
    def _create_field_query(field: str, value: str, query_type: str = "match_phrase", is_sentence: bool = False) -> Dict:
        """
        Create an Elasticsearch query for a specific field.
        
        Args:
            field (str): Field name to search in
            value (str): Search term
            query_type (str): Type of query - 'match_phrase' for exact matching or 'wildcard' for pattern matching
            is_sentence (bool): Whether to treat the value as a complete sentence
            
        Returns:
            Dict: Elasticsearch query dictionary
        """
        if is_sentence:
            # For sentence search, use match_phrase with slop to allow for some word reordering
            return {
                "match_phrase": {
                    field: {
                        "query": value,
                        "slop": 3  # Allow for some flexibility in word positions
                    }
                }
            }
        elif query_type == "wildcard":
            return {"wildcard": {field: {"value": f"*{value}*", "case_insensitive": True}}}
        return {"match_phrase": {field: value}}

    @staticmethod
    def _get_search_payload(queries: List[Dict[str, Union[str, List[str]]]] = None, is_sentence: bool = False) -> dict:
        """
        Generate Elasticsearch query payload for workflow search.
        
        Args:
            queries: List of query dictionaries, each containing:
                    - terms (List[str]): Search terms
                    - fields (List[str]): Fields to search in
                    - operator (str): 'AND' or 'OR' for combining terms
                    - query_type (str): 'match_phrase' or 'wildcard'
            is_sentence (bool): Whether to treat search terms as complete sentences
        
        Returns:
            dict: Complete Elasticsearch query payload
        """
        base_query = {
            "size": 201,
            "_source": True,
            "sort": [
                {"archived": {"order": "asc"}},
                {"stars_count": {"order": "desc"}}
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
                    "must": [
                        {"match": {"_index": "workflows"}}
                    ]
                }
            }
        }

        if not queries:
            base_query["query"]["bool"]["must"].append({"match_all": {}})
            return base_query

        bool_queries = []
        for query_group in queries:
            terms = query_group.get("terms", [])
            fields = query_group.get("fields", [])
            operator = query_group.get("operator", "OR").upper()
            query_type = query_group.get("query_type", "match_phrase")

            if not terms or not fields:
                continue

            field_queries = []
            for term in terms:
                term_queries = []
                for field in fields:
                    term_queries.append(DockstoreSearch._create_field_query(field, term, query_type, is_sentence))
                
                if operator == "OR":
                    field_queries.append({"bool": {"should": term_queries, "minimum_should_match": 1}})
                else:  # AND
                    field_queries.append({"bool": {"must": term_queries}})

            if field_queries:
                bool_queries.append({"bool": {"must" if operator == "AND" else "should": field_queries}})

        if bool_queries:
            base_query["query"]["bool"]["must"].append({"bool": {"must": bool_queries}})

        return base_query

    async def get_workflow_files(self, full_path: str, version: str = None) -> Optional[Dict[str, Any]]:
        """
        Get workflow files using Dockstore's API.
        
        Args:
            full_path (str): Full path of the workflow (e.g., 'github.com/organization/repository')
            version (str): Specific version to fetch (optional)
            
        Returns:
            Optional[Dict[str, Any]]: Dictionary containing workflow files and metadata
        """
        try:
            # Parse workflow path and version
            if ':' in full_path:
                full_path, workflow_name = full_path.split(':', 1)
            else:
                workflow_name = None
            
            headers = {
                "accept": "application/json",
                "accept-language": "zh-CN,zh;q=0.9",
                "content-type": "application/json",
                "origin": "https://dockstore.org",
                "priority": "u=1, i",
                "referer": f"https://dockstore.org/workflows/github.com/{full_path}",
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
            
            async with httpx.AsyncClient() as client:
                # 1. First get the workflow ID
                workflow_url = f"https://dockstore.org/api/workflows/github.com/{full_path}"
                try:
                    workflow_response = await client.get(workflow_url, headers=headers, timeout=30.0)
                    workflow_response.raise_for_status()
                    workflow_info = workflow_response.json()
                    workflow_id = workflow_info.get('id')
                    if not workflow_id:
                        print(f"Could not find workflow ID for: {full_path}")
                        return None
                except httpx.HTTPError as e:
                    if e.response.status_code == 404:
                        print(f"Workflow not found: {full_path}")
                        return None
                    raise
                
                # 2. Get workflow versions
                versions_url = f"https://dockstore.org/api/workflows/{workflow_id}/versions"
                try:
                    versions_response = await client.get(versions_url, headers=headers, timeout=30.0)
                    versions_response.raise_for_status()
                    versions = versions_response.json()
                except httpx.HTTPError as e:
                    if e.response.status_code == 404:
                        print(f"No versions found for workflow: {full_path}")
                        return None
                    raise
                
                # Find the right version
                target_version = None
                for ver in versions:
                    if version and ver.get('name') == version:
                        target_version = ver
                        break
                    elif workflow_name and ver.get('workflowPath', '').endswith(workflow_name):
                        target_version = ver
                        break
                    elif not version and not workflow_name and ver.get('valid'):
                        if not target_version or ver.get('name', '') > target_version.get('name', ''):
                            target_version = ver
                
                if not target_version:
                    print(f"No valid version found for workflow: {full_path}")
                    return None
                
                version_id = target_version.get('id')
                if not version_id:
                    print(f"Could not find version ID for workflow: {full_path}")
                    return None
                
                # 3. Get source files for the version
                files_url = f"https://dockstore.org/api/workflows/{workflow_id}/workflowVersions/{version_id}/sourcefiles"
                try:
                    files_response = await client.get(files_url, headers=headers, timeout=30.0)
                    files_response.raise_for_status()
                    source_files = files_response.json()
                except httpx.HTTPError as e:
                    if e.response.status_code == 404:
                        print(f"No files found for version {target_version.get('name')}")
                        return None
                    raise
                
                # Process different file types
                input_files = {}
                test_files = {}
                secondary_files = []
                primary_descriptor = None
                
                for file in source_files:
                    if not isinstance(file, dict):
                        continue
                        
                    file_path = file.get('path', '').lower()
                    file_type = file.get('type', '')
                    file_content = file.get('content', '')
                    
                    if not file_path or not file_content:
                        continue
                        
                    # Categorize files based on type and name
                    if file_type == 'TEST_FILE' or 'test' in file_path:
                        test_files[file_path] = {
                            'content': file_content,
                            'format': file.get('format', 'unknown')
                        }
                    elif file_type == 'DOCKSTORE_WDL' or file_type == 'DOCKSTORE_CWL':
                        if not primary_descriptor or 'main' in file_path.lower():
                            primary_descriptor = {
                                'content': file_content,
                                'format': 'wdl' if file_type == 'DOCKSTORE_WDL' else 'cwl'
                            }
                        else:
                            secondary_files.append({
                                'path': file_path,
                                'content': file_content,
                                'format': 'wdl' if file_type == 'DOCKSTORE_WDL' else 'cwl'
                            })
                    elif any(f in file_path for f in ['input.json', 'inputs.json', 'params.json', 'parameters.json']):
                        input_files[file_path] = {
                            'content': file_content,
                            'format': 'json'
                        }
                
                # Prepare metadata
                workflow_meta = {
                    'name': workflow_info.get('repository', ''),
                    'description': workflow_info.get('description', ''),
                    'organization': workflow_info.get('organization', ''),
                    'has_checker': workflow_info.get('has_checker', False),
                    'is_trusted': workflow_info.get('is_trusted', False),
                    'last_modified': workflow_info.get('last_modified', None),
                    'last_built': workflow_info.get('last_built', None)
                }
                
                version_meta = {
                    "name": target_version.get('name'),
                    "reference": target_version.get('reference'),
                    "workflow_path": target_version.get('workflow_path'),
                    "verified": target_version.get('verified', False),
                    "verifiedSource": target_version.get('verifiedSource', ''),
                    "is_published": True,
                    "valid": target_version.get('valid', True)
                }
                
                return {
                    "workflow_file": primary_descriptor.get('content') if primary_descriptor else None,
                    "input_files": input_files,
                    "test_files": test_files,
                    "secondary_files": secondary_files,
                    "type": "WDL" if primary_descriptor and primary_descriptor['format'] == 'wdl' else "CWL",
                    "metadata": {
                        **workflow_meta,
                        "version": version_meta
                    }
                }
                
        except httpx.HTTPError as e:
            print(f"HTTP error occurred while fetching workflow files: {e}")
            if hasattr(e, 'response'):
                print(f"Response content: {e.response.text}")
            return None
        except Exception as e:
            print(f"An error occurred while fetching workflow files: {e}")
            return None

    def format_results(self, results: dict, full_output: bool = False) -> str:
        """
        Format search results into human-readable text.
        
        Args:
            results (dict): Raw Elasticsearch response containing workflow data
            full_output (bool): Whether to display full information (True) or only key functional details (False)
            
        Returns:
            str: Formatted text containing workflow information
        """
        if not results or "hits" not in results:
            return "No results found"
            
        total_hits = len(results["hits"].get("hits", []))
        formatted = []
        
        # Add summary information
        summary = [
            "=" * 80,
            f"DOCKSTORE WORKFLOW SEARCH RESULTS",
            f"Total workflows found: {total_hits}",
            "=" * 80,
            ""
        ]
        formatted.extend(summary)
        
        # Process each workflow
        for index, hit in enumerate(results["hits"].get("hits", []), 1):
            source = hit.get("_source", {})
            
            # Get workflow unique identifiers
            workflow_id = source.get('id', 'N/A')  # Internal ID
            workflow_path = source.get('full_workflow_path', 'N/A')  # GA4GH Tool ID format
            workflow_dbid = source.get('dbCreateDate', 'N/A')  # Database creation ID
            
            # Process complex data types
            topics = []
            if source.get('topicAutomatic'):
                if isinstance(source['topicAutomatic'], list):
                    topics.extend(str(t) for t in source['topicAutomatic'])
                else:
                    topics.append(str(source['topicAutomatic']))
            if source.get('topicSelection'):
                if isinstance(source['topicSelection'], list):
                    topics.extend(str(t) for t in source['topicSelection'])
                else:
                    topics.append(str(source['topicSelection']))

            # Process categories
            categories = []
            if source.get('categories'):
                for cat in source['categories']:
                    if isinstance(cat, dict):
                        cat_name = cat.get('topic', '') or cat.get('displayName', '')
                        if cat_name:
                            categories.append(cat_name)
                    else:
                        categories.append(str(cat))

            # Process labels
            labels = []
            if source.get('labels'):
                for label in source['labels']:
                    if isinstance(label, dict):
                        label_value = label.get('value', '')
                        if label_value:
                            labels.append(label_value)
                    else:
                        labels.append(str(label))

            # Build workflow information block
            workflow_block = [
                "-" * 80,
                f"Workflow #{index}",
                "-" * 80,
                "🔍 Identifiers",
                "─" * 40,
                f"Full Path:    {workflow_path}",
                f"Internal ID:  {workflow_id}",
                f"DB Create:    {workflow_dbid}",
                ""
            ]

            if full_output:
                # Full output format
                workflow_block.extend([
                    "📋 Basic Information",
                    "─" * 40,
                    f"Name:         {source.get('name', 'N/A')}",
                    f"Description:  {source.get('description', 'N/A')}",
                    f"Authors:      {', '.join(str(author) for author in source.get('all_authors', ['N/A']))}",
                    f"Organization: {source.get('organization', 'N/A')}",
                    "",
                    "🔧 Technical Details",
                    "─" * 40,
                    f"Descriptor Type:    {source.get('descriptorType', 'N/A')}",
                    f"Descriptor Class:   {source.get('descriptorTypeSubclass', 'N/A')}",
                    f"Workflow Name:      {source.get('workflowName', 'N/A')}",
                    f"Tool Path:          {source.get('tool_path', 'N/A')}",
                    "",
                    "📊 Status",
                    "─" * 40,
                    f"Verified:           {'✓' if source.get('verified', False) else '✗'}",
                    f"Private Access:     {'✓' if source.get('private_access', False) else '✗'}",
                    f"Stars:              {'⭐' * min(source.get('stars_count', 0), 5)} ({source.get('stars_count', 0)})",
                    f"AI Topic Approved:  {'✓' if source.get('approvedAITopic', False) else '✗'}",
                    "",
                    "🔗 Links",
                    "─" * 40,
                    f"Repository:   {source.get('repository', 'N/A')}",
                    f"Git URL:      {source.get('gitUrl', 'N/A')}",
                    f"Provider URL: {source.get('providerUrl', 'N/A')}",
                    "",
                    "📌 Additional Information",
                    "─" * 40,
                    f"Topics:      {', '.join(topics) if topics else 'N/A'}",
                    f"Categories:  {', '.join(categories) if categories else 'N/A'}",
                    f"Labels:      {', '.join(labels) if labels else 'N/A'}",
                    f"Versions:    {len(source.get('workflowVersions', []))} version(s) available",
                ])
            else:
                # Concise output format - focus on functional information
                workflow_block.extend([
                    "📋 Workflow Overview",
                    "─" * 40,
                    f"Name:         {source.get('name', 'N/A')}",
                    f"Description:  {source.get('description', 'N/A')}",
                    "",
                    "🔧 Functionality",
                    "─" * 40,
                    f"Type:         {source.get('descriptorType', 'N/A')} workflow",
                    f"Topics:       {', '.join(topics) if topics else 'N/A'}",
                    f"Categories:   {', '.join(categories) if categories else 'N/A'}",
                ])

            workflow_block.append("")
            workflow_block.append("=" * 80)
            workflow_block.append("")
            formatted.extend(workflow_block)
        
        return "\n".join(formatted)

async def main():
    """
    Main function for the Dockstore workflow search tool.
    
    This function:
    1. Parses command line arguments for search parameters
    2. Constructs query groups based on the provided arguments
    3. Executes the search using the DockstoreSearch client
    4. Formats and displays the results
    5. Saves the raw results to a JSON file
    
    Command Line Arguments:
        -q, --query: Search parameters (repeatable)
            TERM: Search term to look for
            FIELD: Field to search in
            OPERATOR: Boolean operator (AND/OR)
        -t, --type: Query type
            match_phrase: Exact phrase matching (default)
            wildcard: Pattern matching with wildcards
        --outputfull: Display full workflow information (optional)
        --sentence: Treat search term as a complete sentence (optional)
        --get-files: Get workflow files for a specific workflow path
    
    Output:
        - Prints formatted search results to console
        - Saves raw results to 'dockstore_results.json'
    
    Example Usage:
        python dockstore_search.py -q "copy number variation analysis" "description" "AND" --sentence
    """
    try:
        parser = argparse.ArgumentParser(description='Search Dockstore workflows with boolean queries')
        parser.add_argument('-q', '--query', action='append', nargs=3,
                          metavar=('TERM', 'FIELD', 'OPERATOR'),
                          help='Search term, field and operator (AND/OR). Can be specified multiple times.')
        parser.add_argument('-t', '--type', choices=['match_phrase', 'wildcard'],
                          default='match_phrase',
                          help='Query type: match_phrase (default) or wildcard')
        parser.add_argument('--outputfull', action='store_true',
                          help='Display full workflow information')
        parser.add_argument('--sentence', action='store_true',
                          help='Treat search term as a complete sentence')
        parser.add_argument('--get-files', metavar='FULL_PATH',
                          help='Get workflow files for a specific workflow path')
        
        args = parser.parse_args()
        
        client = DockstoreSearch()
        
        if args.get_files:
            files = await client.get_workflow_files(args.get_files)
            if files:
                # Create a directory for the workflow files
                workflow_dir = f"workflow_{files['metadata']['name'].replace(' ', '_')}"
                os.makedirs(workflow_dir, exist_ok=True)
                
                # Save workflow file with appropriate extension
                workflow_ext = files['type'].lower()
                workflow_filename = os.path.join(workflow_dir, f"workflow.{workflow_ext}")
                if files.get('workflow_file'):
                    with open(workflow_filename, 'w', encoding='utf-8') as f:
                        f.write(files['workflow_file'])
                    print(f"Primary workflow descriptor saved as '{workflow_filename}'")
                
                # Save input files
                input_dir = os.path.join(workflow_dir, 'inputs')
                os.makedirs(input_dir, exist_ok=True)
                for path, file_info in files.get('input_files', {}).items():
                    filename = os.path.join(input_dir, path.split('/')[-1])
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(file_info['content'])
                    print(f"Input file saved as '{filename}'")
                
                # Save test files
                test_dir = os.path.join(workflow_dir, 'tests')
                os.makedirs(test_dir, exist_ok=True)
                for path, file_info in files.get('test_files', {}).items():
                    filename = os.path.join(test_dir, path.split('/')[-1])
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(file_info['content'])
                    print(f"Test file saved as '{filename}'")
                
                # Save secondary descriptor files
                secondary_dir = os.path.join(workflow_dir, 'secondary')
                os.makedirs(secondary_dir, exist_ok=True)
                for idx, file_info in files.get('secondary_files', []), 1:
                    filename = os.path.join(secondary_dir, f"{idx}_{file_info['path'].split('/')[-1]}")
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(file_info['content'])
                    print(f"Secondary descriptor saved as '{filename}'")
                
                # Save versions information
                with open(os.path.join(workflow_dir, 'versions.json'), 'w', encoding='utf-8') as f:
                    json.dump(files['versions'], f, indent=2, ensure_ascii=False)
                print("Version information saved as 'versions.json'")
                
                # Save metadata
                with open(os.path.join(workflow_dir, 'workflow_metadata.json'), 'w', encoding='utf-8') as f:
                    json.dump(files['metadata'], f, indent=2, ensure_ascii=False)
                print("Workflow metadata saved as 'workflow_metadata.json'")
                
                # Print workflow information
                print("\nWorkflow Information:")
                print(f"Type: {files['type']}")
                print(f"Name: {files['metadata'].get('name', 'N/A')}")
                print(f"Version: {files['metadata']['version']['name']}")
                print(f"Verified: {'Yes' if files['metadata']['version']['verified'] else 'No'}")
                if files['metadata']['version'].get('verifiedSource'):
                    print(f"Verified Source: {files['metadata']['version']['verifiedSource']}")
                print(f"Published: {'Yes' if files['metadata']['version']['is_published'] else 'No'}")
                print(f"Last Modified: {files['metadata']['version'].get('last_modified', 'N/A')}")
                if files['metadata'].get('description'):
                    print(f"\nDescription: {files['metadata']['description']}")
                
                # Print validation status if available
                validation = files['metadata']['version'].get('validation_status')
                if validation:
                    print("\nValidation Status:")
                    print(f"Valid: {'Yes' if validation.get('valid', False) else 'No'}")
                    if validation.get('message'):
                        print(f"Message: {validation['message']}")
            else:
                print("Could not retrieve workflow files")
            return
        
        # Build queries
        queries = []
        if args.query:
            current_group = {"terms": [], "fields": [], "operator": "AND", "query_type": args.type}
            current_operator = None
            
            for term, field, operator in args.query:
                if current_operator and operator != current_operator:
                    queries.append(current_group)
                    current_group = {"terms": [], "fields": [], "operator": operator.upper(), "query_type": args.type}
                
                current_group["terms"].append(term)
                current_group["fields"].append(field)
                current_operator = operator.upper()
            
            if current_group["terms"]:
                queries.append(current_group)
        
        results = await client.search(queries, args.sentence)
        if results:
            # Print formatted results
            print(client.format_results(results, args.outputfull))
            
            # Save raw JSON results with full path
            result_path = os.path.abspath('dockstore_results.json')
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"\n结果文件已保存到: {result_path}")
        else:
            print("No results found or an error occurred")
            
    except Exception as e:
        print(f"Error in main: {e}")

if __name__ == "__main__":
    asyncio.run(main())