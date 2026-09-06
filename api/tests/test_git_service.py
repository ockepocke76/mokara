"""
Unit tests for Git service (GitHub API integration).

Tests branch creation, file commits, history retrieval using mock GitHub API.
"""

import pytest
import os
import requests
from unittest.mock import Mock, patch, MagicMock
from services.git_service import GitHubService


class TestGitHubService:
    """Test suite for GitHubService."""
    
    @pytest.fixture
    def git_service(self):
        """Create Git service instance with test credentials."""
        with patch.dict(os.environ, {
            'GITHUB_REPO_OWNER': 'test-org',
            'GITHUB_REPO_NAME': 'test-repo',
            'GITHUB_TOKEN': 'test-token-123'
        }):
            service = GitHubService()
            yield service
    
    @pytest.fixture
    def mock_response(self):
        """Create mock HTTP response."""
        response = Mock()
        response.status_code = 200
        response.headers = {'X-RateLimit-Remaining': '5000'}
        response.raise_for_status = Mock()
        return response
    
    def test_initialization(self, git_service):
        """Test service initializes with correct configuration."""
        assert git_service.repo_owner == 'test-org'
        assert git_service.repo_name == 'test-repo'
        assert git_service.token == 'test-token-123'
        assert 'test-org/test-repo' in git_service.base_url
    
    def test_initialization_missing_token(self):
        """Test initialization fails without token."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="GitHub token not provided"):
                GitHubService()
    
    @patch('services.git_service.requests.request')
    def test_create_branch_from_main(self, mock_request, git_service, mock_response):
        """Test creating a branch from main."""
        # Mock GET ref response (get main SHA)
        get_response = Mock()
        get_response.status_code = 200
        get_response.json.return_value = {
            'object': {'sha': 'abc123def456'}
        }
        get_response.raise_for_status = Mock()
        get_response.headers = {'X-RateLimit-Remaining': '5000'}
        
        # Mock POST create branch response
        post_response = Mock()
        post_response.status_code = 201
        post_response.json.return_value = {
            'ref': 'refs/heads/strategies/user-123/strat-456',
            'object': {'sha': 'abc123def456'}
        }
        post_response.raise_for_status = Mock()
        post_response.headers = {'X-RateLimit-Remaining': '4999'}
        
        mock_request.side_effect = [get_response, post_response]
        
        # Create branch
        result = git_service.create_branch('strategies/user-123/strat-456')
        
        assert result['branch_name'] == 'strategies/user-123/strat-456'
        assert result['sha'] == 'abc123def456'
        assert 'already_exists' not in result
    
    @patch('services.git_service.requests.request')
    def test_create_branch_already_exists(self, mock_request, git_service):
        """Test creating a branch that already exists."""
        # Mock GET ref response
        get_response = Mock()
        get_response.status_code = 200
        get_response.json.return_value = {'object': {'sha': 'abc123'}}
        get_response.raise_for_status = Mock()
        get_response.headers = {'X-RateLimit-Remaining': '5000'}
        
        # Mock POST create branch (422 conflict)
        post_response = Mock()
        post_response.status_code = 422
        post_response.raise_for_status.side_effect = requests.HTTPError("Conflict", response=post_response)
        post_response.headers = {'X-RateLimit-Remaining': '4999'}
        
        # Mock GET existing branch
        existing_response = Mock()
        existing_response.status_code = 200
        existing_response.json.return_value = {
            'ref': 'refs/heads/test-branch',
            'object': {'sha': 'existing123'}
        }
        existing_response.raise_for_status = Mock()
        existing_response.headers = {'X-RateLimit-Remaining': '4998'}
        
        mock_request.side_effect = [get_response, post_response, existing_response]
        
        result = git_service.create_branch('test-branch')
        
        assert result['already_exists'] is True
        assert result['sha'] == 'existing123'
    
    @patch('services.git_service.requests.request')
    def test_commit_file_create_new(self, mock_request, git_service):
        """Test committing a new file."""
        # Mock GET file (404 - doesn't exist)
        get_response = Mock()
        get_response.status_code = 404
        get_response.raise_for_status.side_effect = requests.HTTPError("Not found", response=get_response)
        get_response.headers = {'X-RateLimit-Remaining': '5000'}
        
        # Mock PUT create file
        put_response = Mock()
        put_response.status_code = 201
        put_response.json.return_value = {
            'commit': {'sha': 'newfile123'}
        }
        put_response.raise_for_status = Mock()
        put_response.headers = {'X-RateLimit-Remaining': '4999'}
        
        mock_request.side_effect = [get_response, put_response]
        
        commit_sha = git_service.commit_file(
            branch_name='test-branch',
            file_path='strategy.py',
            content='print("hello")',
            message='Initial commit'
        )
        
        assert commit_sha == 'newfile123'
    
    @patch('services.git_service.requests.request')
    def test_commit_file_update_existing(self, mock_request, git_service):
        """Test updating an existing file."""
        # Mock GET file (exists)
        get_response = Mock()
        get_response.status_code = 200
        get_response.json.return_value = {'sha': 'oldfile123'}
        get_response.raise_for_status = Mock()
        get_response.headers = {'X-RateLimit-Remaining': '5000'}
        
        # Mock PUT update file
        put_response = Mock()
        put_response.status_code = 200
        put_response.json.return_value = {
            'commit': {'sha': 'updatedfile456'}
        }
        put_response.raise_for_status = Mock()
        put_response.headers = {'X-RateLimit-Remaining': '4999'}
        
        mock_request.side_effect = [get_response, put_response]
        
        commit_sha = git_service.commit_file(
            branch_name='test-branch',
            file_path='strategy.py',
            content='print("updated")',
            message='Update strategy'
        )
        
        assert commit_sha == 'updatedfile456'
    
    @patch('services.git_service.requests.request')
    def test_get_file_content(self, mock_request, git_service):
        """Test fetching file content."""
        import base64
        
        content_original = 'print("test strategy")'
        content_encoded = base64.b64encode(content_original.encode()).decode()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'content': content_encoded}
        mock_response.raise_for_status = Mock()
        mock_response.headers = {'X-RateLimit-Remaining': '5000'}
        
        mock_request.return_value = mock_response
        
        content = git_service.get_file_content('test-branch', 'strategy.py')
        
        assert content == content_original
    
    @patch('services.git_service.requests.request')
    def test_get_commit_history(self, mock_request, git_service):
        """Test fetching commit history."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'sha': 'commit1',
                'commit': {
                    'message': 'Initial commit',
                    'author': {'name': 'User A', 'date': '2024-01-01T12:00:00Z'}
                },
                'html_url': 'https://github.com/test/repo/commit/commit1'
            },
            {
                'sha': 'commit2',
                'commit': {
                    'message': 'Update strategy',
                    'author': {'name': 'User B', 'date': '2024-01-02T12:00:00Z'}
                },
                'html_url': 'https://github.com/test/repo/commit/commit2'
            }
        ]
        mock_response.raise_for_status = Mock()
        mock_response.headers = {'X-RateLimit-Remaining': '5000'}
        
        mock_request.return_value = mock_response
        
        commits = git_service.get_commit_history('test-branch', limit=10)
        
        assert len(commits) == 2
        assert commits[0]['sha'] == 'commit1'
        assert commits[0]['message'] == 'Initial commit'
        assert commits[1]['author'] == 'User B'
    
    @patch('services.git_service.requests.request')
    def test_delete_branch(self, mock_request, git_service):
        """Test deleting a branch."""
        mock_response = Mock()
        mock_response.status_code = 204
        mock_response.raise_for_status = Mock()
        mock_response.headers = {'X-RateLimit-Remaining': '5000'}
        
        mock_request.return_value = mock_response
        
        result = git_service.delete_branch('test-branch')
        
        assert result is True
    
    @patch('services.git_service.requests.get')
    def test_check_rate_limit(self, mock_get, git_service):
        """Test checking rate limit."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'rate': {
                'limit': 5000,
                'remaining': 4850,
                'reset': 1234567890
            }
        }
        
        mock_get.return_value = mock_response
        
        rate_info = git_service.check_rate_limit()
        
        assert rate_info['limit'] == 5000
        assert rate_info['remaining'] == 4850


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
