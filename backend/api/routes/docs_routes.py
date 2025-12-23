"""
Documentation API routes - codebase search and source code retrieval.
"""

import os
import re
import subprocess
from fastapi import APIRouter, Query
from typing import Optional

router = APIRouter(tags=["Documentation"])

# Project root directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Directories to search (relative to PROJECT_ROOT)
SEARCH_DIRS = [
    "core",
    "quant",
    "trading",
    "data",
    "gamma",
    "backtest",
    "validation",
    "ai",
    "utils",
    "backend",
]

# File extensions to search
ALLOWED_EXTENSIONS = [".py", ".ts", ".tsx", ".js", ".jsx"]


@router.get("/api/docs/search")
async def search_codebase(
    query: str = Query(..., min_length=2, description="Search query"),
    file_type: Optional[str] = Query(None, description="File extension filter (e.g., 'py', 'ts')"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of results")
):
    """
    Search the codebase for calculations, functions, or patterns.
    Returns matching lines with file path, line number, and context.
    """
    try:
        results = []

        # Build grep command
        grep_args = ["grep", "-rn", "-i"]

        # Add file type filter
        if file_type:
            grep_args.extend(["--include", f"*.{file_type}"])
        else:
            for ext in ALLOWED_EXTENSIONS:
                grep_args.extend(["--include", f"*{ext}"])

        grep_args.append(query)

        # Add search directories
        for search_dir in SEARCH_DIRS:
            full_path = os.path.join(PROJECT_ROOT, search_dir)
            if os.path.exists(full_path):
                grep_args.append(full_path)

        # Run grep
        try:
            result = subprocess.run(
                grep_args,
                capture_output=True,
                text=True,
                timeout=10,
                cwd=PROJECT_ROOT
            )
            output = result.stdout
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Search timed out", "results": []}
        except Exception as e:
            return {"success": False, "error": str(e), "results": []}

        # Parse grep output
        for line in output.strip().split("\n"):
            if not line:
                continue

            # Format: file:line_number:content
            match = re.match(r'^(.+?):(\d+):(.*)$', line)
            if match:
                file_path, line_num, content = match.groups()

                # Make path relative to project root
                rel_path = os.path.relpath(file_path, PROJECT_ROOT)

                results.append({
                    "file": rel_path,
                    "line": int(line_num),
                    "content": content.strip(),
                    "match_type": classify_match(content)
                })

                if len(results) >= limit:
                    break

        return {
            "success": True,
            "query": query,
            "total": len(results),
            "results": results
        }

    except Exception as e:
        return {"success": False, "error": str(e), "results": []}


@router.get("/api/docs/source")
async def get_source_code(
    file: str = Query(..., description="File path relative to project root"),
    line: int = Query(..., ge=1, description="Line number to center on"),
    context: int = Query(10, ge=1, le=50, description="Lines of context before and after")
):
    """
    Get source code snippet from a specific file and line number.
    Returns the target line plus surrounding context.
    """
    try:
        # Validate file path (prevent directory traversal)
        if ".." in file or file.startswith("/"):
            return {"success": False, "error": "Invalid file path"}

        full_path = os.path.join(PROJECT_ROOT, file)

        if not os.path.exists(full_path):
            return {"success": False, "error": f"File not found: {file}"}

        if not os.path.isfile(full_path):
            return {"success": False, "error": "Not a file"}

        # Check extension
        ext = os.path.splitext(file)[1]
        if ext not in ALLOWED_EXTENSIONS:
            return {"success": False, "error": f"File type not allowed: {ext}"}

        # Read file
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        total_lines = len(lines)

        if line > total_lines:
            return {"success": False, "error": f"Line {line} exceeds file length ({total_lines})"}

        # Calculate range
        start_line = max(1, line - context)
        end_line = min(total_lines, line + context)

        # Extract lines
        code_lines = []
        for i in range(start_line - 1, end_line):
            code_lines.append({
                "line_number": i + 1,
                "content": lines[i].rstrip('\n'),
                "is_target": (i + 1) == line
            })

        return {
            "success": True,
            "file": file,
            "target_line": line,
            "start_line": start_line,
            "end_line": end_line,
            "total_lines": total_lines,
            "code": code_lines,
            "language": get_language(ext)
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/docs/functions")
async def list_functions(
    file: str = Query(..., description="File path relative to project root")
):
    """
    List all function/method definitions in a file.
    """
    try:
        # Validate file path
        if ".." in file or file.startswith("/"):
            return {"success": False, "error": "Invalid file path"}

        full_path = os.path.join(PROJECT_ROOT, file)

        if not os.path.exists(full_path):
            return {"success": False, "error": f"File not found: {file}"}

        ext = os.path.splitext(file)[1]

        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            lines = content.split('\n')

        functions = []

        if ext == '.py':
            # Python function pattern
            pattern = r'^\s*(async\s+)?def\s+(\w+)\s*\('
            for i, line in enumerate(lines, 1):
                match = re.match(pattern, line)
                if match:
                    is_async = bool(match.group(1))
                    func_name = match.group(2)
                    functions.append({
                        "name": func_name,
                        "line": i,
                        "type": "async function" if is_async else "function"
                    })

            # Also find class definitions
            class_pattern = r'^\s*class\s+(\w+)'
            for i, line in enumerate(lines, 1):
                match = re.match(class_pattern, line)
                if match:
                    functions.append({
                        "name": match.group(1),
                        "line": i,
                        "type": "class"
                    })

        elif ext in ['.ts', '.tsx', '.js', '.jsx']:
            # JavaScript/TypeScript function patterns
            patterns = [
                (r'^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)', 'function'),
                (r'^\s*(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>', 'arrow function'),
                (r'^\s*(?:export\s+)?(?:default\s+)?class\s+(\w+)', 'class'),
            ]

            for i, line in enumerate(lines, 1):
                for pattern, func_type in patterns:
                    match = re.match(pattern, line)
                    if match:
                        functions.append({
                            "name": match.group(1),
                            "line": i,
                            "type": func_type
                        })
                        break

        return {
            "success": True,
            "file": file,
            "functions": sorted(functions, key=lambda x: x['line'])
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def classify_match(content: str) -> str:
    """Classify what type of code match this is."""
    content_lower = content.lower()

    if 'def calculate' in content_lower or 'def compute' in content_lower:
        return 'calculation_function'
    elif 'def ' in content_lower:
        return 'function'
    elif 'class ' in content_lower:
        return 'class'
    elif '=' in content and ('formula' in content_lower or 'calculation' in content_lower):
        return 'formula'
    elif '#' in content and 'calculate' in content_lower:
        return 'comment'
    else:
        return 'code'


def get_language(ext: str) -> str:
    """Get language name from file extension."""
    languages = {
        '.py': 'python',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.js': 'javascript',
        '.jsx': 'javascript',
    }
    return languages.get(ext, 'text')
