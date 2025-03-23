"""Dockstore Workflow Downloader

A standalone tool for downloading workflow files from Dockstore. 
Supports multiple workflow path formats and custom save locations.

Basic Usage:
   # Linux/macOS Terminal
   python fetch_wdl_from_dockstore.py \
       --full_workflow_path "github.com/broadinstitute/TAG-public/CNV-Profiler" \
       --results_dir "/path/to/workflows"

Supported Path Formats:
    1. Dockstore URL:
       https://dockstore.org/workflows/github.com/broadinstitute/TAG-public/CNV-Profiler

    2. GitHub Path:
       github.com/broadinstitute/TAG-public/CNV-Profiler

    3. Short Path:
       broadinstitute/TAG-public/CNV-Profiler

Arguments:
    --full_workflow_path: Workflow path (supports all formats above)
    --results_dir: Directory for saving workflow files (created if not exists)

Output Files:
    1. Workflow Description Files (*.wdl, *.cwl)
    2. Input Parameter Files (*.json)
"""

from typing import Any, Dict, List, Optional, Union
from pathlib import Path
from uuid import uuid4
import argparse
import asyncio
import httpx
import json
import os

class DockstoreDownloader:
    """Dockstore workflow download client"""
    
    API_BASE = "https://dockstore.org/api/api/ga4gh/v2/extended/tools/entry/_search"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    def __init__(self) -> None:
        """Initialize downloader"""
        self.search_url = self.API_BASE
        self.headers = {
            "accept": "application/json",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "origin": "https://dockstore.org",
            "user-agent": self.USER_AGENT,
            "x-dockstore-ui": "2.13.3",
            "x-request-id": str(uuid4()),
            "x-session-id": str(uuid4())
        }

    def _build_search_body(self, workflow_path: str) -> Dict[str, Any]:
        """Build search request body"""
        return {
            "size": 1,
            "_source": [
                "full_workflow_path", "name", "description", 
                "organization", "workflowVersions"
            ],
            "query": {
                "bool": {
                    "must": [
                        {"match": {"_index": "workflows"}},
                        {"match_phrase": {"full_workflow_path": workflow_path}}
                    ]
                }
            }
        }

    async def find_workflow(self, workflow_path: str) -> Optional[Dict[str, Any]]:
        """Find workflow by path
        
        Supports the following formats:
        1. github.com/org/repo/workflow
        2. org/repo/workflow
        3. https://dockstore.org/workflows/github.com/org/repo/workflow
        """
        # Handle Dockstore URL
        if workflow_path.startswith(("http://", "https://")):
            if "/workflows/" in workflow_path:
                # Extract workflow path
                path_parts = workflow_path.split("/workflows/")
                if len(path_parts) > 1:
                    workflow_path = path_parts[1]
                    # Remove github.com/ prefix if present
                    if workflow_path.startswith("github.com/"):
                        workflow_path = workflow_path.replace("github.com/", "", 1)
        
        # Ensure path doesn't start with github.com/
        if workflow_path.startswith("github.com/"):
            workflow_path = workflow_path.replace("github.com/", "", 1)
        
        # Build search request
        search_body = self._build_search_body(f"github.com/{workflow_path}")
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.search_url,
                    json=search_body,
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                results = response.json()
                
                if results.get("hits", {}).get("hits"):
                    # Save raw JSON results with full path
                    result_path = os.path.abspath('dockstore_results.json')
                    with open(result_path, 'w', encoding='utf-8') as f:
                        json.dump(results, f, indent=2, ensure_ascii=False)
                        print(f"\n结果文件已保存到: {result_path}")
                    return results["hits"]["hits"][0]
                return None
                
            except Exception as e:
                print(f"Failed to find workflow: {e}")
                if isinstance(e, httpx.HTTPError) and hasattr(e, 'response'):
                    print(f"Response content: {e.response.text}")
                return None

    async def save_workflow_files(self, workflow: Dict, results_dir: str) -> Optional[str]:
        """Save workflow files
        
        Args:
            workflow (Dict): Workflow information
            results_dir (str): Path to results directory (required)
            
        Returns:
            Optional[str]: Absolute path to saved directory, None if failed
        """
        try:
            source = workflow.get("_source", {})
            workflow_path = source.get("full_workflow_path")
            
            if not workflow_path:
                return None
                
            # Create directory using provided results_dir
            dir_name = Path(workflow_path).name
            wdl_dir = Path(results_dir) / dir_name
            wdl_dir.mkdir(parents=True, exist_ok=True)
            
            # Collect and save WDL files
            wdl_files = []

            for version in source.get("workflowVersions", []):
                for source_file in version.get("sourceFiles", []):
                    file_path = source_file.get("path", "")
                    content = source_file.get("content", "")
                    
                    if not (file_path and content):
                        continue
                        
                    if file_path.endswith((".wdl", ".cwl")):
                        wdl_files.append((file_path, content))
                        # Save file to specified directory
                        full_path = wdl_dir / Path(file_path).name
                        with open(full_path, "w", encoding="utf-8") as f:
                            f.write(content)
                    else:
                        print("选中的工作流没有可用的WDL格式程序")
                        return {"error": "No WDL-formatted program is available for the selected workflow. Check the workflow configuration"}
                
            return str(wdl_dir.absolute())
            
        except Exception as e:
            print(f"Error saving files: {e}")
            return None

async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Download workflow files from Dockstore')
    
    parser.add_argument('--full_workflow_path', 
                       required=True,
                       help='Full workflow path (e.g., github.com/broadinstitute/warp/...)')
    parser.add_argument('--results_dir',
                       required=True,
                       help='Path to workflow files save directory')
    
    args = parser.parse_args()
    downloader = DockstoreDownloader()
    
    try:
        print(f"\nSearching for workflow: {args.full_workflow_path}")
        workflow = await downloader.find_workflow(args.full_workflow_path)
        
        if not workflow:
            print("Workflow not found")
            return
            
        print("\nStarting workflow download...")
        save_dir = await downloader.save_workflow_files(workflow, args.results_dir)
            
    except Exception as e:
        print(f"Execution error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())