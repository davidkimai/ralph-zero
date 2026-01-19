"""Agent SDK wrapper for programmatic Claude invocation.

This module provides the AgentSDKInvoker class which uses Claude Agent SDK
for programmatic file manipulation, enabling autonomous development loops.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Result from agent invocation."""
    
    output: str
    is_complete: bool
    failure_reason: Optional[str] = None
    exit_code: int = 0


class AgentSDKInvoker:
    """
    Invokes Claude via Agent SDK for programmatic file manipulation.
    
    Uses Claude Agent SDK with:
    - Built-in tools: Read, Write, Edit, Glob, Grep, Bash
    - Permission mode: acceptEdits (auto-approve file operations)
    - Fresh context per invocation (stateless)
    
    This enables autonomous development workflows where Claude can:
    - Read and edit files directly
    - Run quality gates via Bash tool
    - Report completion via structured output
    """
    
    def __init__(self, model: str = "claude-3-7-sonnet-20250219") -> None:
        """
        Initialize AgentSDKInvoker.
        
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
                "Agent SDK requires an API key for programmatic invocation."
            )
        
        logger.info(f"AgentSDKInvoker initialized (model={model})")
    
    def invoke(
        self,
        prompt: str,
        working_dir: Path,
        iteration: int,
        timeout: int = 3600
    ) -> AgentResult:
        """
        Invoke Claude with prompt using Agent SDK.
        
        Args:
            prompt: The prompt to send to Claude
            working_dir: Working directory for file operations
            iteration: Current iteration number (for logging)
            timeout: Timeout in seconds (default: 1 hour)
        
        Returns:
            AgentResult with output and completion status
        """
        logger.info(f"Invoking Agent SDK for iteration {iteration}")
        logger.debug(f"Working directory: {working_dir}")
        
        try:
            # Import SDK (deferred to catch import errors)
            try:
                from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
            except ImportError as e:
                logger.error("claude-agent-sdk not installed. Run: pip install claude-agent-sdk")
                return AgentResult(
                    output="",
                    is_complete=False,
                    failure_reason="SDK_NOT_INSTALLED",
                    exit_code=2
                )
            
            # Configure SDK options for autonomous workflow
            options = ClaudeAgentOptions(
                # Auto-approve file edits and filesystem commands
                permission_mode="acceptEdits",
                
                # Enable file manipulation tools
                allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
                
                # Set working directory
                working_directory=str(working_dir),
                
                # Model selection
                model=self.model,
            )
            
            logger.debug(f"SDK options: permission_mode=acceptEdits, tools={options.allowed_tools}")
            
            # Create SDK client (fresh context per invocation)
            client = ClaudeSDKClient(api_key=self.api_key)
            
            # Invoke agent
            logger.info("Executing agent with SDK...")
            result = client.query(
                prompt=prompt,
                options=options,
                timeout=timeout
            )
            
            # Extract output
            output = self._extract_output(result)
            
            logger.info(f"Agent SDK completed ({len(output)} chars output)")
            
            # Check for completion signal
            is_complete, failure_reason = self._check_completion_signal(output)
            
            return AgentResult(
                output=output,
                is_complete=is_complete,
                failure_reason=failure_reason,
                exit_code=0 if is_complete else 1
            )
        
        except Exception as e:
            logger.error(f"Agent SDK invocation failed: {e}", exc_info=True)
            return AgentResult(
                output=str(e),
                is_complete=False,
                failure_reason=f"SDK_ERROR: {str(e)}",
                exit_code=2
            )
    
    def _extract_output(self, result: any) -> str:
        """
        Extract text output from SDK result.
        
        Args:
            result: SDK query result
        
        Returns:
            Extracted text output
        """
        # SDK result structure varies - handle common formats
        if isinstance(result, str):
            return result
        
        if hasattr(result, "content"):
            return str(result.content)
        
        if hasattr(result, "text"):
            return str(result.text)
        
        if hasattr(result, "output"):
            return str(result.output)
        
        # Fallback: convert to string
        return str(result)
    
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
            - (True, None) if complete
            - (False, reason) if failed with reason
            - (False, "NO_COMPLETION_SIGNAL") if no signal found
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
        Get information about configured SDK.
        
        Returns:
            Dict with SDK details
        """
        return {
            "mode": "sdk",
            "model": self.model,
            "api_key_set": bool(self.api_key),
        }
