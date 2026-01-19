"""Direct Anthropic API wrapper for ralph-zero.

This module provides stateless agent invocation aligned with ralph-loop principles.
Each invocation has ZERO conversation history - fresh context only.
"""

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Result from agent invocation."""
    
    output: str
    is_complete: bool
    failure_reason: Optional[str] = None
    exit_code: int = 0


class RalphAgentAPI:
    """
    Direct Anthropic API wrapper for ralph-zero orchestration.
    
    Key Principles:
    - STATELESS: Zero conversation history between iterations
    - FRESH CONTEXT: Context from AGENTS.md + progress.txt only
    - TOOL CALLING: Direct file manipulation via custom tools
    - SYNCHRONOUS: Simple, predictable orchestration
    
    This aligns perfectly with Geoffrey Huntley's ralph-loop pattern.
    """
    
    def __init__(self, model: str = "claude-3-7-sonnet-20250219") -> None:
        """
        Initialize RalphAgentAPI.
        
        Args:
            model: Claude model to use
        
        Raises:
            RuntimeError: If ANTHROPIC_API_KEY not found
        """
        self.model = model
        
        # Check for API key
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY environment variable not set. "
                "Direct API requires an API key for invocation."
            )
        
        # Initialize Anthropic client
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.api_key)
        except ImportError:
            raise RuntimeError(
                "anthropic package not installed. Run: pip install anthropic"
            )
        
        logger.info(f"RalphAgentAPI initialized (model={model})")
    
    def invoke(
        self,
        prompt: str,
        working_dir: Path,
        iteration: int,
        timeout: int = 3600
    ) -> AgentResult:
        """
        Invoke Claude with FRESH CONTEXT (zero history).
        
        Args:
            prompt: The prompt to send to Claude
            working_dir: Working directory for file operations
            iteration: Current iteration number (for logging)
            timeout: Timeout in seconds (default: 1 hour)
        
        Returns:
            AgentResult with output and completion status
        """
        logger.info(f"Invoking Direct API for iteration {iteration}")
        logger.debug(f"Working directory: {working_dir}")
        logger.debug(f"Prompt length: {len(prompt)} chars")
        
        try:
            # Build tools for file manipulation
            tools = self._build_tools()
            
            # Create messages with ZERO history (fresh context)
            messages = [{"role": "user", "content": prompt}]
            
            logger.info(f"Calling API with {len(tools)} tools, fresh context")
            
            # Call Anthropic API - NO conversation history!
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8192,  # Ensure headroom for completion signal
                messages=messages,  # CRITICAL: No history
                tools=tools,
                temperature=0.7,
                system=(
                    "You MUST end your response with either <promise>COMPLETE</promise> if successful, or "
                    "<promise>FAILED: reason</promise> if you encounter blocking issues. This signal is CRITICAL "
                    "for the orchestrator to know you've finished."
                ),
            )
            
            # Handle tool calling loop
            output_parts = []
            max_turns = 20  # Prevent infinite loops
            turn = 0
            
            while response.stop_reason == "tool_use" and turn < max_turns:
                turn += 1
                logger.debug(f"Tool use turn {turn}/{max_turns}")
                
                # Extract tool calls
                tool_results = []
                for content_block in response.content:
                    if content_block.type == "tool_use":
                        tool_name = content_block.name
                        tool_input = content_block.input
                        tool_id = content_block.id
                        
                        logger.info(f"Executing tool: {tool_name}")
                        
                        # Execute tool
                        result = self._execute_tool(
                            tool_name, tool_input, working_dir
                        )
                        
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": result
                        })
                
                # Append messages for next turn
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
                
                # Continue conversation
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=8192,
                    messages=messages,
                    tools=tools,
                    temperature=0.7,
                    system=(
                        "You MUST end your response with either <promise>COMPLETE</promise> if successful, or "
                        "<promise>FAILED: reason</promise> if you encounter blocking issues. This signal is CRITICAL "
                        "for the orchestrator to know you've finished."
                    ),
                )
            
            # Extract final text output
            output = ""
            for content_block in response.content:
                if hasattr(content_block, "text"):
                    output += content_block.text
            
            logger.info(f"API completed ({len(output)} chars output)")
            
            # Check for completion signal
            is_complete, failure_reason = self._check_completion_signal(output)
            
            return AgentResult(
                output=output,
                is_complete=is_complete,
                failure_reason=failure_reason,
                exit_code=0 if is_complete else 1
            )
        
        except Exception as e:
            logger.error(f"API invocation failed: {e}", exc_info=True)
            return AgentResult(
                output=str(e),
                is_complete=False,
                failure_reason=f"API_ERROR: {str(e)}",
                exit_code=2
            )
    
    def _build_tools(self) -> List[Dict[str, Any]]:
        """
        Build tool definitions for file manipulation.
        
        Returns:
            List of tool definitions
        """
        return [
            {
                "name": "read_file",
                "description": "Read the complete contents of a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the file to read (relative or absolute)"
                        }
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "write_file",
                "description": "Create a new file or completely overwrite an existing file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path where the file should be created/written"
                        },
                        "content": {
                            "type": "string",
                            "description": "Complete content to write to the file"
                        }
                    },
                    "required": ["path", "content"]
                }
            },
            {
                "name": "edit_file",
                "description": "Make precise edits to an existing file by replacing old content with new content",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the file to edit"
                        },
                        "old_content": {
                            "type": "string",
                            "description": "Exact content to find and replace (must match precisely)"
                        },
                        "new_content": {
                            "type": "string",
                            "description": "New content to replace the old content with"
                        }
                    },
                    "required": ["path", "old_content", "new_content"]
                }
            },
            {
                "name": "run_bash",
                "description": "Execute a bash command (for quality gates, git, tests, etc.)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Bash command to execute"
                        }
                    },
                    "required": ["command"]
                }
            }
        ]
    
    def _execute_tool(
        self, tool_name: str, tool_input: Dict[str, Any], working_dir: Path
    ) -> str:
        """
        Execute a tool and return result.
        
        Args:
            tool_name: Name of tool to execute
            tool_input: Tool input parameters
            working_dir: Working directory for operations
        
        Returns:
            Tool execution result as string
        """
        try:
            if tool_name == "read_file":
                return self._tool_read_file(tool_input["path"], working_dir)
            
            elif tool_name == "write_file":
                return self._tool_write_file(
                    tool_input["path"], tool_input["content"], working_dir
                )
            
            elif tool_name == "edit_file":
                return self._tool_edit_file(
                    tool_input["path"],
                    tool_input["old_content"],
                    tool_input["new_content"],
                    working_dir
                )
            
            elif tool_name == "run_bash":
                return self._tool_run_bash(tool_input["command"], working_dir)
            
            else:
                return f"Error: Unknown tool '{tool_name}'"
        
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}", exc_info=True)
            return f"Error executing {tool_name}: {str(e)}"
    
    def _tool_read_file(self, path: str, working_dir: Path) -> str:
        """Read file tool implementation."""
        file_path = working_dir / path
        try:
            content = file_path.read_text(encoding="utf-8")
            logger.debug(f"Read {len(content)} chars from {path}")
            return content
        except Exception as e:
            return f"Error reading {path}: {str(e)}"
    
    def _tool_write_file(self, path: str, content: str, working_dir: Path) -> str:
        """Write file tool implementation."""
        file_path = working_dir / path
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            logger.info(f"Wrote {len(content)} chars to {path}")
            return f"Successfully wrote {len(content)} characters to {path}"
        except Exception as e:
            return f"Error writing {path}: {str(e)}"
    
    def _tool_edit_file(
        self, path: str, old_content: str, new_content: str, working_dir: Path
    ) -> str:
        """Edit file tool implementation."""
        file_path = working_dir / path
        try:
            current_content = file_path.read_text(encoding="utf-8")
            
            if old_content not in current_content:
                return f"Error: old content not found in {path}"
            
            new_file_content = current_content.replace(old_content, new_content, 1)
            file_path.write_text(new_file_content, encoding="utf-8")
            
            logger.info(f"Edited {path}: replaced {len(old_content)} chars with {len(new_content)} chars")
            return f"Successfully edited {path}"
        except Exception as e:
            return f"Error editing {path}: {str(e)}"
    
    def _tool_run_bash(self, command: str, working_dir: Path) -> str:
        """Run bash command tool implementation."""
        try:
            logger.info(f"Running bash: {command}")
            result = subprocess.run(
                command,
                shell=True,
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout for commands
            )
            
            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR:\n{result.stderr}"
            
            if result.returncode != 0:
                output += f"\nExit code: {result.returncode}"
            
            logger.debug(f"Bash output ({len(output)} chars): {output[:200]}...")
            return output
        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after 300s"
        except Exception as e:
            return f"Error running bash: {str(e)}"
    
    def _check_completion_signal(self, output: str) -> Tuple[bool, Optional[str]]:
        """
        Check if agent reported completion via signal.
        
        Looks for:
        - <promise>COMPLETE</promise>
        - <promise>FAILED: reason</promise>
        
        Args:
            output: Agent output
        
        Returns:
            Tuple of (is_complete, failure_reason)
        """
        if "<promise>COMPLETE</promise>" in output:
            logger.info("Agent reported completion via <promise> signal")
            return (True, None)
        
        if "<promise>FAILED:" in output:
            # Extract reason
            start = output.find("<promise>FAILED:")
            end = output.find("</promise>", start)
            if end != -1:
                reason = output[start + len("<promise>FAILED:") : end].strip()
                logger.warning(f"Agent reported failure: {reason}")
                return (False, reason)
            else:
                logger.warning("Agent reported failure but malformed signal")
                return (False, "MALFORMED_FAILURE_SIGNAL")
        
        logger.warning("Agent did not report completion or failure signal")
        return (False, "NO_COMPLETION_SIGNAL")
    
    def get_info(self) -> dict:
        """
        Get information about configured API.
        
        Returns:
            Dict with API details
        """
        return {
            "mode": "api",
            "model": self.model,
            "api_key_set": bool(self.api_key),
        }
