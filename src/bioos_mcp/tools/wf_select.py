import os
import json
import httpx
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Tuple

class WorkflowSelector:
    """工作流选择器"""
    
    def __init__(self, workflow_path: str, download: bool = False):
        """初始化
        
        Args:
            workflow_path: 要查找的工作流路径
            download: 是否下载WDL文件
        """
        self.workflow_path = workflow_path
        self.download = download
        self.wdl_dir = None
    
    def find_workflow(self, results: Dict) -> Optional[Dict]:
        """查找指定路径的工作流
        
        Args:
            results: Dockstore搜索结果
            
        Returns:
            Optional[Dict]: 找到的工作流信息或None
        """
        if not results or "hits" not in results:
            return None
            
        for workflow in results["hits"]["hits"]:
            source = workflow.get("_source", {})
            if source.get("full_workflow_path") == self.workflow_path:
                return workflow
        return None
    
    def extract_wdl_files(self, workflow: Dict) -> List[Tuple[str, str]]:
        """提取工作流中的WDL文件
        
        Args:
            workflow: 工作流信息
            
        Returns:
            List[Tuple[str, str]]: (文件路径, 文件内容)列表
        """
        wdl_files = []
        source = workflow.get("_source", {})
        
        for version in source.get("workflowVersions", []):
            for source_file in version.get("sourceFiles", []):
                file_path = source_file.get("path", "")
                if file_path.endswith(".wdl"):
                    content = source_file.get("content", "")
                    if content:  # 只收集有内容的WDL文件
                        wdl_files.append((file_path, content))
        
        return wdl_files
    
    def save_wdl_files(self, wdl_files: List[Tuple[str, str]]) -> Optional[Path]:
        """保存WDL文件
        
        Args:
            wdl_files: (文件路径, 文件内容)列表
            
        Returns:
            Optional[Path]: WDL文件保存目录的绝对路径
        """
        if not wdl_files:
            return None
            
        # 使用工作流名称作为目录名
        dir_name = Path(self.workflow_path).name
        wdl_dir = Path.cwd() / "wdl_files" / dir_name
        wdl_dir.mkdir(parents=True, exist_ok=True)
        
        for file_path, content in wdl_files:
            # 保持原始目录结构
            full_path = wdl_dir / Path(file_path).name
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
                
        return wdl_dir.absolute()

async def main(workflow_path: str, download: bool = False):
    """主函数
    
    Args:
        workflow_path: 工作流路径
        download: 是否下载WDL文件
    """
    try:
        with open("dockstore_results.json", "r", encoding="utf-8") as f:
            search_results = json.load(f)
            
        selector = WorkflowSelector(workflow_path, download)
        workflow = selector.find_workflow(search_results)
        
        if not workflow:
            print(f"未找到工作流: {workflow_path}")
            return
            
        wdl_files = selector.extract_wdl_files(workflow)
        
        if not wdl_files:
            print("未找到WDL文件")
            return
            
        if download:
            wdl_dir = selector.save_wdl_files(wdl_files)
            if wdl_dir:
                print(f"WDL文件已保存到: {wdl_dir}")
                print(f"找到 {len(wdl_files)} 个WDL文件:")
                for file_path, _ in wdl_files:
                    print(f"  - {file_path}")
            else:
                print("保存WDL文件失败")
        else:
            print(f"找到 {len(wdl_files)} 个WDL文件:")
            for file_path, _ in wdl_files:
                print(f"  - {file_path}")
                
    except FileNotFoundError:
        print("错误：找不到输入文件 dockstore_results.json")
    except json.JSONDecodeError:
        print("错误：JSON 格式无效")
    except Exception as e:
        print(f"发生错误：{str(e)}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python wf_select.py <workflow_path> [--download]")
        sys.exit(1)
        
    workflow_path = sys.argv[1]
    download = "--download" in sys.argv[2:]
    
    asyncio.run(main(workflow_path, download))