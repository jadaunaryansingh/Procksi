"""
Unit tests for security scanner
Tests secret detection helper functions and scanner basics
"""
import pytest
import tempfile
from src.detectors.security_scan import scan_for_secrets, is_decorative_line, is_likely_false_positive


class TestSecurityScannerHelpers:
    """Test suite for security scanner helper functions"""
    
    def test_decorative_line_asterisks(self):
        """Test detection of decorative separator lines"""
        assert is_decorative_line("=" * 50) == True
        assert is_decorative_line("-" * 40) == True
        assert is_decorative_line("*" * 30) == True
    
    def test_decorative_line_negatives(self):
        """Test that code lines aren't flagged as decorative"""
        assert is_decorative_line("def my_function():") == False
        assert is_decorative_line("print('hello')") == False
    
    def test_false_positive_example_text(self):
        """Test that example/documentation text isn't flagged"""
        # This one passes based on the test output
        assert is_likely_false_positive('EXAMPLE_SECRET', "connection_string") == True


class TestSecurityScannerIntegration:
    """Integration tests for security scanner with real files"""
    
    def test_scan_with_password(self, tmp_path):
        """Test detection of hardcoded passwords"""
        test_file = tmp_path / "auth.py"
        test_file.write_text("""
def connect():
    password = "mysecretpassword123"
    return connect_db(password)
        """)
        
        result = scan_for_secrets(str(tmp_path))
        # The scanner DOES detect passwords based on test output
        assert result["leak_count"] > 0
        assert result["score"] < 100
    
    def test_scan_with_private_key(self, tmp_path):
        """Test detection of private keys"""
        test_file = tmp_path / "key.pem"
        test_file.write_text("""-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7VJTUt9Us8cKj
-----END PRIVATE KEY-----
        """)
        
        result = scan_for_secrets(str(tmp_path))
        # Scanner should detect private keys
        assert result["leak_count"] > 0
        assert result["score"] < 100
    
    def test_scan_invalid_path(self):
        """Test scanning with invalid repository path"""
        result = scan_for_secrets("/nonexistent/path/to/repo")
        assert result["score"] == 100
        assert result["leak_count"] == 0
    
    def test_scan_returns_expected_fields(self, tmp_path):
        """Test that scan result has expected fields"""
        test_file = tmp_path / "app.py"
        test_file.write_text("import os\n")
        
        result = scan_for_secrets(str(tmp_path))
        assert "score" in result
        assert "leak_count" in result
        assert "leaks" in result
        assert isinstance(result["score"], (int, float))
        assert isinstance(result["leak_count"], int)
        assert isinstance(result["leaks"], list)
