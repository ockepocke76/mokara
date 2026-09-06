"""
Git Service for Strategy Version Control

Provides GitHub API integration for strategy storage and versioning.
Uses GitHub REST API to manage branches, commits, and file operations.
"""

import os
import logging
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime


class GitHubService:
    """
    GitHub API client for strategy version control.
    
    Handles:
    - Branch creation and management
    - File commits
    - Commit history retrieval
    - Diff generation
    """
    
    def __init__(self, repo_owner: str = None, repo_name: str = None, token: str = None):
        """
        Initialize GitHub service.
        
        Args:
            repo_owner: GitHub username or organization (e.g., "your-org")
            repo_name: Repository name (e.g., "btc-simulator-strategies")
            token: GitHub Personal Access Token or App token
        """
        # Load from environment if not provided
        self.repo_owner = repo_owner or os.getenv('GITHUB_REPO_OWNER')
        self.repo_name = repo_name or os.getenv('GITHUB_REPO_NAME', 'btc-simulator-strategies')
        self.token = token or os.getenv('GITHUB_TOKEN')
        
        if not self.token:
            raise ValueError("GitHub token not provided. Set GITHUB_TOKEN environment variable.")
        
        if not self.repo_owner:
            raise ValueError("GitHub repo owner not provided. Set GITHUB_REPO_OWNER environment variable.")
        
        self.base_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}"
        self.headers = {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        logging.info(f"GitHubService initialized for {self.repo_owner}/{self.repo_name}")
    
    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """
        Make authenticated request to GitHub API.
        
        Args:
            method: HTTP method (GET, POST, PUT, etc.)
            endpoint: API endpoint (will be appended to base_url)
            **kwargs: Additional arguments for requests
        
        Returns:
            Response object
        
        Raises:
            requests.HTTPError: On API errors
        """
        if endpoint:
            url = f"{self.base_url}/{endpoint}"
        else:
            url = self.base_url
        
        # Add headers
        if 'headers' in kwargs:
            kwargs['headers'].update(self.headers)
        else:
            kwargs['headers'] = self.headers
        
        response = requests.request(method, url, **kwargs)
        
        # Log rate limit info
        if 'X-RateLimit-Remaining' in response.headers:
            remaining = response.headers['X-RateLimit-Remaining']
            logging.debug(f"GitHub API rate limit remaining: {remaining}")
        
        # Raise on error
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            if response.status_code == 404:
                # 404 is often expected (check existence), so log as debug/warning
                logging.debug(f"GitHub API 404 (Not Found): {endpoint}")
            else:
                logging.error(f"GitHub API error: {response.status_code} - {response.text}")
            raise
        
        return response
    
    def get_default_branch(self) -> str:
        """Get the repository's default branch."""
        try:
            response = self._request('GET', '')
            return response.json().get('default_branch', 'main')
        except requests.HTTPError:
            return 'main'

    def create_branch(self, branch_name: str, from_commit_sha: str = None, from_branch: str = "main") -> Dict[str, Any]:
        """
        Create a new branch from an existing commit or branch.
        
        Args:
            branch_name: Name of branch to create (e.g., "strategies/user-123/strat-456")
            from_commit_sha: SHA to branch from (optional, overrides from_branch)
            from_branch: Branch name to branch from (default: "main")
        
        Returns:
            Dict with branch info including ref and sha
        
        Raises:
            requests.HTTPError: If branch creation fails
        """
        # Get SHA if not provided
        if not from_commit_sha:
            try:
                # Get SHA of from_branch
                ref_response = self._request('GET', f'git/ref/heads/{from_branch}')
                from_commit_sha = ref_response.json()['object']['sha']
                logging.info(f"Resolved {from_branch} to SHA: {from_commit_sha[:7]}")
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    default_branch = self.get_default_branch()
                    if default_branch != from_branch:
                        logging.info(f"Branch {from_branch} not found. Falling back to default branch: {default_branch}")
                        ref_response = self._request('GET', f'git/ref/heads/{default_branch}')
                        from_commit_sha = ref_response.json()['object']['sha']
                    else:
                        raise
                else:
                    raise
        
        # Create branch reference
        ref = f"refs/heads/{branch_name}"
        payload = {
            'ref': ref,
            'sha': from_commit_sha
        }
        
        try:
            response = self._request('POST', 'git/refs', json=payload)
            branch_info = response.json()
            
            logging.info(f"Created branch: {branch_name} from {from_commit_sha[:7]}")
            
            return {
                'ref': branch_info['ref'],
                'sha': branch_info['object']['sha'],
                'branch_name': branch_name
            }
        
        except requests.HTTPError as e:
            if e.response.status_code == 422:
                logging.warning(f"Branch {branch_name} already exists")
                # Return existing branch info
                existing = self._request('GET', f'git/ref/heads/{branch_name}')
                return {
                    'ref': existing.json()['ref'],
                    'sha': existing.json()['object']['sha'],
                    'branch_name': branch_name,
                    'already_exists': True
                }
            raise
    
    def commit_file(self, branch_name: str, file_path: str, content: str, message: str) -> str:
        """
        Create or update a file with a commit.
        
        Args:
            branch_name: Branch to commit to
            file_path: Path to file in repo (e.g., "strategy.py")
            content: File content (string)
            message: Commit message
        
        Returns:
            SHA of the new commit
        
        Raises:
            requests.HTTPError: If commit fails
        """
        # Check if file exists to get current SHA
        existing_sha = None
        try:
            file_response = self._request('GET', f'contents/{file_path}?ref={branch_name}')
            existing_sha = file_response.json()['sha']
            logging.debug(f"File {file_path} exists, SHA: {existing_sha[:7]}")
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                logging.debug(f"File {file_path} does not exist, will create")
            else:
                raise
        
        # Commit file (create or update)
        import base64
        encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        
        payload = {
            'message': message,
            'content': encoded_content,
            'branch': branch_name
        }
        
        if existing_sha:
            payload['sha'] = existing_sha
        
        response = self._request('PUT', f'contents/{file_path}', json=payload)
        commit_info = response.json()
        
        commit_sha = commit_info['commit']['sha']
        logging.info(f"Committed {file_path} to {branch_name}: {commit_sha[:7]} - {message}")
        
        return commit_sha
    
    def get_file_content(self, branch_name: str, file_path: str, commit_sha: str = None) -> str:
        """
        Fetch file content from a branch or specific commit.
        
        Args:
            branch_name: Branch name
            file_path: Path to file
            commit_sha: Optional specific commit SHA
        
        Returns:
            File content as string
        
        Raises:
            requests.HTTPError: If file not found
        """
        ref = commit_sha if commit_sha else branch_name
        response = self._request('GET', f'contents/{file_path}?ref={ref}')
        
        import base64
        content_encoded = response.json()['content']
        content = base64.b64decode(content_encoded).decode('utf-8')
        
        logging.debug(f"Fetched {file_path} from {ref}")
        return content
    
    def get_file_content_safe(self, branch_name: str, file_path: str, commit_sha: str = None) -> Optional[str]:
        """
        Fetch file content, returning None instead of raising on 404.
        
        Args:
            branch_name: Branch name
            file_path: Path to file
            commit_sha: Optional specific commit SHA
        
        Returns:
            File content as string, or None if not found
        """
        try:
            return self.get_file_content(branch_name, file_path, commit_sha)
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                logging.debug(f"File {file_path} not found in {branch_name}")
                return None
            raise
    
    def commit_multiple_files(
        self, 
        branch_name: str, 
        files: Dict[str, str],
        message: str
    ) -> str:
        """
        Commit multiple files atomically in a single commit using Git tree API.
        
        This is more efficient than multiple sequential commits and ensures
        all files are committed together or not at all.
        
        Args:
            branch_name: Branch to commit to
            files: Dictionary mapping file paths to content {file_path: content}
            message: Commit message
        
        Returns:
            SHA of the new commit
        
        Raises:
            requests.HTTPError: If commit fails
        """
        import base64
        
        # 1. Get current branch reference to find parent commit
        ref_response = self._request('GET', f'git/ref/heads/{branch_name}')
        parent_sha = ref_response.json()['object']['sha']
        
        # 2. Get parent commit to find its tree
        commit_response = self._request('GET', f'git/commits/{parent_sha}')
        parent_tree_sha = commit_response.json()['tree']['sha']
        
        # 3. Create blobs for each file
        tree_items = []
        for file_path, content in files.items():
            # Create blob
            blob_data = {
                'content': content,
                'encoding': 'utf-8'
            }
            blob_response = self._request('POST', 'git/blobs', json=blob_data)
            blob_sha = blob_response.json()['sha']
            
            # Add to tree
            tree_items.append({
                'path': file_path,
                'mode': '100644',  # Regular file
                'type': 'blob',
                'sha': blob_sha
            })
            
            logging.debug(f"Created blob for {file_path}: {blob_sha[:7]}")
        
        # 4. Create new tree
        tree_data = {
            'base_tree': parent_tree_sha,
            'tree': tree_items
        }
        tree_response = self._request('POST', 'git/trees', json=tree_data)
        new_tree_sha = tree_response.json()['sha']
        
        # 5. Create commit
        commit_data = {
            'message': message,
            'tree': new_tree_sha,
            'parents': [parent_sha]
        }
        commit_response = self._request('POST', 'git/commits', json=commit_data)
        new_commit_sha = commit_response.json()['sha']
        
        # 6. Update branch reference
        ref_update_data = {
            'sha': new_commit_sha,
            'force': False
        }
        self._request('PATCH', f'git/refs/heads/{branch_name}', json=ref_update_data)
        
        file_list = ', '.join(files.keys())
        logging.info(f"Committed {len(files)} files to {branch_name}: {new_commit_sha[:7]} - {file_list}")
        
        return new_commit_sha
    
    def get_metadata(self, branch_name: str, commit_sha: str = None) -> Optional[Dict[str, Any]]:
        """
        Fetch and parse metadata.json from a branch or commit.
        
        Args:
            branch_name: Branch name
            commit_sha: Optional specific commit SHA
        
        Returns:
            Parsed metadata dictionary, or None if not found or invalid
        """
        import json
        
        metadata_content = self.get_file_content_safe(branch_name, 'metadata.json', commit_sha)
        
        if not metadata_content:
            return None
        
        try:
            metadata = json.loads(metadata_content)
            logging.debug(f"Loaded metadata from {branch_name}")
            return metadata
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON in metadata.json: {e}")
            return None
    
    def get_commit_history(self, branch_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get commit history for a branch.
        
        Args:
            branch_name: Branch name
            limit: Maximum number of commits to return
        
        Returns:
            List of commit dictionaries with sha, message, author, date
        """
        response = self._request('GET', f'commits?sha={branch_name}&per_page={limit}')
        commits_raw = response.json()
        
        commits = []
        for commit in commits_raw:
            commits.append({
                'sha': commit['sha'],
                'message': commit['commit']['message'],
                'author': commit['commit']['author']['name'],
                'date': commit['commit']['author']['date'],
                'url': commit['html_url']
            })
        
        logging.debug(f"Fetched {len(commits)} commits from {branch_name}")
        return commits
    
    def get_diff(self, commit_sha_old: str, commit_sha_new: str) -> str:
        """
        Get diff between two commits.
        
        Args:
            commit_sha_old: Older commit SHA
            commit_sha_new: Newer commit SHA
        
        Returns:
            Diff as string (unified diff format)
        """
        # GitHub compare API
        response = self._request('GET', f'compare/{commit_sha_old}...{commit_sha_new}')
        compare_data = response.json()
        
        # Extract diff from files
        diff_lines = []
        for file in compare_data.get('files', []):
            if 'patch' in file:
                diff_lines.append(f"--- {file['filename']}")
                diff_lines.append(file['patch'])
        
        diff = '\n'.join(diff_lines)
        logging.debug(f"Generated diff between {commit_sha_old[:7]}...{commit_sha_new[:7]}")
        
        return diff
    
    def delete_branch(self, branch_name: str) -> bool:
        """
        Delete a branch.
        
        Args:
            branch_name: Branch to delete
        
        Returns:
            True if deleted successfully
        """
        try:
            self._request('DELETE', f'git/refs/heads/{branch_name}')
            logging.info(f"Deleted branch: {branch_name}")
            return True
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                logging.warning(f"Branch {branch_name} does not exist")
                return False
            raise
    
    @staticmethod
    def compute_file_sha(content: str) -> str:
        """
        Compute the Git blob SHA for a given content string.
        This allows checking if content matches a commit without an API call.
        """
        import hashlib
        
        # Git blob format: "blob <length>\0<content>"
        content_bytes = content.encode('utf-8')
        header = f"blob {len(content_bytes)}\0".encode('utf-8')
        data = header + content_bytes
        
        return hashlib.sha1(data).hexdigest()

    def check_rate_limit(self) -> Dict[str, Any]:
        """
        Check current rate limit status.
        
        Returns:
            Dict with rate limit info
        """
        response = requests.get(
            'https://api.github.com/rate_limit',
            headers=self.headers
        )
        return response.json()['rate']


# Global instance (lazy-loaded)
_git_service_instance = None


def get_git_service() -> GitHubService:
    """
    Get singleton GitHubService instance.
    
    Returns:
        GitHubService instance
    """
    global _git_service_instance
    
    if _git_service_instance is None:
        _git_service_instance = GitHubService()
    
    return _git_service_instance
