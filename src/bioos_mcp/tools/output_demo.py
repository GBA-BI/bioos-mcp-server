import json
from typing import Dict, List

class WorkflowFormatter:
    """Dockstore 工作流信息格式化工具"""
    
    @staticmethod
    def format_workflow(workflow: Dict) -> str:
        """格式化单个工作流信息"""
        source = workflow.get("_source", {})
        
        # 检查是否有源文件内容
        has_source_files = False
        for version in source.get("workflowVersions", []):
            for source_file in version.get("sourceFiles", []):
                if source_file.get("content"):
                    has_source_files = True
                    break
            if has_source_files:
                break
                
        # 如果没有源文件内容，则跳过该工作流
        if not has_source_files:
            return ""
        
        # 构建基本信息部分(只保留前两行描述)
        description = source.get('description', 'N/A').split('\n')[:2]
        basic_info = [
            f"# 工作流基本信息 (ID: {workflow.get('_id', 'N/A')})",
            f"命名空间：{source.get('namespace', 'N/A')}",
            f"完整路径：{source.get('full_workflow_path', 'N/A')}",
            f"工作流名称：{source.get('name', 'N/A')}",
            f"描述信息：{'\n'.join(description)}",
            f"所属组织：{source.get('organization', 'N/A')}\n"
        ]
        
        # 构建版本信息部分
        versions = []
        for idx, version in enumerate(source.get("workflowVersions", []), 1):
            version_files = []
            
            # 只收集有内容的源文件
            for source_file in version.get("sourceFiles", []):
                if source_file.get("content"):
                    version_files.append(source_file)
            
            # 如果该版本没有源文件内容，则跳过
            if not version_files:
                continue
                
            version_info = [
                f"## 版本 {idx}",
                f"版本ID：{version.get('id', 'N/A')}",
                f"Git仓库版本：{version.get('reference', 'N/A')}",
                "源文件列表："
            ]
            
            # 添加源文件信息
            for source_file in version_files:
                version_info.append(f"- 文件路径：{source_file.get('path', 'N/A')}")
            
            versions.extend(version_info)
        
        # 如果没有包含源文件内容的版本，返回空字符串
        if not versions:
            return ""
        
        # 合并所有信息
        return "\n".join(basic_info + versions)

    @staticmethod
    def format_search_results(results: Dict) -> str:
        """格式化搜索结果"""
        if not results or "hits" not in results:
            return "未找到搜索结果"
            
        workflows = results["hits"]["hits"]
        formatted_results = []
        
        for workflow in workflows:
            formatted_workflow = WorkflowFormatter.format_workflow(workflow)
            if formatted_workflow:  # 只添加非空结果
                formatted_results.append(formatted_workflow)
                formatted_results.append("-" * 80 + "\n")
            
        if formatted_results:
            return "\n".join(formatted_results)
        else:
            return "未找到包含源文件内容的工作流"

    @classmethod
    def format_results_from_file(cls, input_file: str, output_file: str = "formatted_workflows.md") -> str:
        """从文件读取并格式化搜索结果
        
        Args:
            input_file: 输入的JSON文件路径
            output_file: 输出的Markdown文件路径，默认为 formatted_workflows.md
            
        Returns:
            str: 格式化后的文本内容
            
        Raises:
            FileNotFoundError: 输入文件不存在
            json.JSONDecodeError: JSON格式无效
        """
        try:
            with open(input_file, "r", encoding="utf-8") as f:
                search_results = json.load(f)
                
            formatted_output = cls.format_search_results(search_results)
            
            # 如果提供了输出文件路径，则保存结果
            if output_file:
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(formatted_output)
                print(f"格式化完成，结果已写入 {output_file}")
                
            return formatted_output
            
        except FileNotFoundError:
            raise FileNotFoundError(f"错误：找不到输入文件 {input_file}")
        except json.JSONDecodeError:
            raise json.JSONDecodeError("错误：JSON 格式无效")

def main():
    """主函数"""
    try:
        formatter = WorkflowFormatter()
        formatter.format_results_from_file("dockstore_results.json")
        
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(str(e))
    except Exception as e:
        print(f"发生错误：{str(e)}")

if __name__ == "__main__":
    main()