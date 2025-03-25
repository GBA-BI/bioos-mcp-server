"""
Dockstore Workflow Downloader

This tool downloads workflows from Dockstore based on a URL.
It maintains the original directory structure of the workflow files.

Usage:
    python fetch_wdl_from_dockstore.py <workflow_url> [output_dir]

Examples:
    # 下载工作流到当前目录
    python fetch_wdl_from_dockstore.py https://dockstore.miracle.ac.cn/workflows/git.miracle.ac.cn/gzlab/mrnaseq/mRNAseq

    # 下载工作流到指定目录
    python fetch_wdl_from_dockstore.py https://dockstore.miracle.ac.cn/workflows/git.miracle.ac.cn/gzlab/mrnaseq/mRNAseq ./workflows
"""

import os
import sys
import json
import re
import argparse
import asyncio
import httpx
import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4


class DockstoreDownloader:
    """Dockstore workflow downloader client."""
    
    BASE_URL = "https://dockstore.miracle.ac.cn/api"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    def __init__(self) -> None:
        """Initialize the DockstoreDownloader client."""
        self.headers = {
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "User-Agent": self.USER_AGENT,
            "X-Request-ID": str(uuid4()),
        }
    
    @staticmethod
    def parse_workflow_url(url: str) -> Tuple[Optional[str], Optional[str]]:
        """Parse organization and workflow name from a Dockstore URL."""
        # 处理完整URL
        if url.startswith(('http://', 'https://')):
            parsed = urlparse(url)
            path = parsed.path
        else:
            # 处理只有路径部分的URL
            path = url
        
        # 移除 /workflows/ 前缀 (如果存在)
        if '/workflows/' in path:
            path = path.split('/workflows/')[-1]
        
        # 提取组织和工作流名
        parts = path.strip('/').split('/')
        
        # 格式可能有多种:
        # 1. git.miracle.ac.cn/gzlab/mrnaseq/mRNAseq
        # 2. github.com/broadinstitute/gatk-sv/module00c-metrics
        # 3. gzlab/mrnaseq/mRNAseq
        
        if len(parts) >= 3:
            # 判断第一部分是否包含域名 (.com, .cn, .org 等)
            if any(domain in parts[0] for domain in ['.com', '.cn', '.org', '.io', '.net']):
                # 域名后面的部分通常是组织名
                org = parts[1]
                # 工作流名是最后一部分
                workflow_name = parts[-1]
            else:
                # 如果没有域名，则第一部分是组织名
                org = parts[0]
                # 工作流名是最后一部分
                workflow_name = parts[-1]
                
            print(f"成功解析 URL: 组织={org}, 工作流={workflow_name}")
            return org, workflow_name
        
        print(f"无法从URL '{url}' 解析组织名和工作流名")
        return None, None

    async def get_published_workflows(self, organization: str) -> Optional[List[Dict[str, Any]]]:
        """Get all published workflows for an organization."""
        url = f"{self.BASE_URL}/workflows/organization/{organization}/published"
        print(f"查询组织 {organization} 的已发布工作流")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self.headers)
                
                if response.status_code != 200:
                    print(f"查询已发布工作流失败，状态码: {response.status_code}")
                    print(f"错误响应: {response.text}")
                    return None
                
                result = response.json()
                workflow_count = len(result)
                print(f"找到 {workflow_count} 个已发布工作流")
                return result
        except Exception as e:
            print(f"查询已发布工作流时出错: {str(e)}")
            return None

    async def find_workflow_by_name(
        self, workflows: List[Dict[str, Any]], workflow_name: str
    ) -> Optional[Dict[str, Any]]:
        """Find a specific workflow by name from a list of workflows."""
        if not workflows:
            return None
            
        # 尝试直接匹配
        matching_workflows = [
            wf for wf in workflows 
            if wf.get("workflowName") == workflow_name
        ]
        
        # 如果没有直接匹配，尝试不区分大小写匹配
        if not matching_workflows:
            matching_workflows = [
                wf for wf in workflows 
                if wf.get("workflowName", "").lower() == workflow_name.lower()
            ]
        
        # 如果仍没有匹配，尝试匹配 repository 名称
        if not matching_workflows:
            matching_workflows = [
                wf for wf in workflows 
                if wf.get("repository", "").lower() == workflow_name.lower()
            ]
            
        # 尝试部分匹配名称
        if not matching_workflows:
            matching_workflows = [
                wf for wf in workflows 
                if workflow_name.lower() in wf.get("workflowName", "").lower() or
                workflow_name.lower() in wf.get("repository", "").lower()
            ]
        
        if not matching_workflows:
            print(f"未找到名为 {workflow_name} 的工作流")
            print("可用的工作流:")
            for wf in workflows[:10]:  # 只显示前10个
                print(f"  - {wf.get('workflowName')} (存储库: {wf.get('repository')})")
            return None
        
        # 如果有多个匹配项，使用最新的一个
        if len(matching_workflows) > 1:
            print(f"发现 {len(matching_workflows)} 个名为 {workflow_name} 的工作流，使用最新版本")
            # 按照更新时间排序
            matching_workflows.sort(
                key=lambda x: x.get("lastUpdated", ""), 
                reverse=True
            )
        
        workflow = matching_workflows[0]
        print(f"已找到工作流: ID={workflow.get('id')}, 路径={workflow.get('full_workflow_path')}")
        return workflow

    async def get_latest_workflow_version(
        self, workflow: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Get the latest version of a workflow."""
        workflow_versions = workflow.get("workflowVersions", [])
        
        if not workflow_versions:
            print(f"工作流 {workflow.get('id')} 没有可用版本")
            return None
        
        # 寻找最新的稳定版本，如果没有则使用最新的任意版本
        stable_versions = [v for v in workflow_versions if v.get("valid", False)]
        target_versions = stable_versions if stable_versions else workflow_versions
        
        # 按照更新时间排序
        target_versions.sort(
            key=lambda x: x.get("lastUpdated", ""),
            reverse=True
        )
        
        latest_version = target_versions[0]
        print(f"使用工作流版本: ID={latest_version.get('id')}, 名称={latest_version.get('name')}")
        return latest_version

    async def get_source_files(
        self, workflow_id: int, version_id: int
    ) -> Optional[List[Dict[str, Any]]]:
        """Get source files for a specific workflow version."""
        url = f"{self.BASE_URL}/workflows/{workflow_id}/workflowVersions/{version_id}/sourcefiles"
        print(f"获取工作流 {workflow_id} 版本 {version_id} 的源文件")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self.headers)
                
                if response.status_code != 200:
                    print(f"获取源文件失败，状态码: {response.status_code}")
                    print(f"错误响应: {response.text}")
                    return None
                
                result = response.json()
                file_count = len(result)
                print(f"找到 {file_count} 个源文件")
                return result
        except Exception as e:
            print(f"获取源文件时出错: {str(e)}")
            return None

    async def download_workflow(
        self, 
        organization: str, 
        workflow_name: str, 
        output_dir: str
    ) -> bool:
        """Download a workflow based on organization and workflow name."""
        # 1. 获取组织已发布的工作流
        workflows = await self.get_published_workflows(organization)
        if not workflows:
            print(f"组织 {organization} 没有已发布的工作流")
            return False
        
        # 2. 根据名称查找工作流
        workflow = await self.find_workflow_by_name(workflows, workflow_name)
        if not workflow:
            return False
        
        # 3. 获取最新版本
        latest_version = await self.get_latest_workflow_version(workflow)
        if not latest_version:
            return False
        
        # 4. 获取源文件
        workflow_id = workflow.get("id")
        version_id = latest_version.get("id")
        if not workflow_id or not version_id:
            print("找不到有效的工作流 ID 或版本 ID")
            return False
            
        source_files = await self.get_source_files(workflow_id, version_id)
        if not source_files:
            return False
        
        # 5. 创建输出目录
        base_output_dir = Path(output_dir)
        workflow_output_dir = base_output_dir / f"{organization}_{workflow_name}"
        workflow_output_dir.mkdir(parents=True, exist_ok=True)
        
        # 6. 下载和保存文件
        downloaded_count = 0
        for file in source_files:
            path = file.get("absolutePath", "")
            content = file.get("content", "")
            
            if not path or not content:
                continue
            
            # 去掉路径前面的斜杠，以便与输出目录正确组合
            if path.startswith("/"):
                path = path[1:]
            
            file_path = workflow_output_dir / path
            
            # 确保父目录存在
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入文件内容
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
            downloaded_count += 1
            print(f"已保存文件: {file_path}")

        print(f"已成功下载 {downloaded_count} 个文件到 {workflow_output_dir}")
        
        # 7. 保存工作流元数据
        current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        metadata = {
            "organization": organization,
            "workflowName": workflow_name,
            "workflowId": workflow_id,
            "versionId": version_id,
            "versionName": latest_version.get("name"),
            "fullWorkflowPath": workflow.get("full_workflow_path"),
            "descriptorType": workflow.get("descriptorType", ""),
            "downloadDate": current_time
        }
        
        metadata_path = workflow_output_dir / "workflow_metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
            
        print(f"已保存工作流元数据到 {metadata_path}")
        return True
    
    async def download_workflow_from_url(
        self,
        url: str,
        output_dir: str
    ) -> bool:
        """Download a workflow based on its URL."""
        # 解析URL，获取组织和工作流名称
        organization, workflow_name = self.parse_workflow_url(url)
        
        if not organization or not workflow_name:
            print(f"无法从URL解析组织和工作流名称: {url}")
            print("请确保URL格式正确，例如: https://dockstore.miracle.ac.cn/workflows/git.miracle.ac.cn/gzlab/mrnaseq/mRNAseq")
            return False
        
        print(f"从URL解析出: 组织={organization}, 工作流={workflow_name}")
        
        # 使用解析出的组织和工作流名称下载
        return await self.download_workflow(organization, workflow_name, output_dir)


async def main():
    """Main function for the Dockstore workflow downloader."""
    parser = argparse.ArgumentParser(description='Dockstore 工作流下载工具')
    
    # 简化参数 - 只需要 URL 和输出目录
    parser.add_argument('url', help='工作流 URL (例如: https://dockstore.miracle.ac.cn/workflows/git.miracle.ac.cn/gzlab/mrnaseq/mRNAseq)')
    parser.add_argument('output_dir', nargs='?', default='.', help='输出目录路径 (默认为当前目录)')
    
    args = parser.parse_args()
    
    downloader = DockstoreDownloader()
    
    # 直接使用 URL 下载
    success = await downloader.download_workflow_from_url(args.url, args.output_dir)
    
    if success:
        print("工作流下载成功!")
        return 0
    else:
        print("工作流下载失败!")
        return 1


# 支持 MCP 服务器调用的入口点
async def download_from_mcp(config):
    """MCP server entry point for Dockstore workflow download."""
    downloader = DockstoreDownloader()
    
    url = config.get("url")
    output_path = config.get("output_path", ".")
    
    if not url:
        return {"error": "必须提供 URL 参数"}
    
    success = await downloader.download_workflow_from_url(url, output_path)
    
    if not success:
        return {"error": "工作流下载失败，请检查 URL 或网络连接"}
    
    # 解析组织和工作流名称，以获取保存路径
    org, workflow_name = downloader.parse_workflow_url(url)
    if not org or not workflow_name:
        return {"error": "无法从 URL 解析组织和工作流名称"}
        
    save_dir = Path(output_path) / f"{org}_{workflow_name}"
    
    # 获取已下载的文件列表
    files = []
    for root, _, filenames in os.walk(save_dir):
        for filename in filenames:
            file_path = Path(root) / filename
            rel_path = file_path.relative_to(save_dir)
            files.append(str(rel_path))
    
    return {
        "success": True + "\n",
        "save_directory": str(save_dir) + "\n",
        "organization": org +"\n",
        "workflow_name": workflow_name +"\n",
        "files": files
    }


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(result)