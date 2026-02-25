# -*- coding:utf-8 -*-
"""
WhatsApp Cloud API Integration Client

HTTP client for Meta Graph API v24.0 to manage WhatsApp Business messaging.
Handles authentication, retries with exponential backoff, and error parsing.

Reference: https://developers.facebook.com/docs/whatsapp/cloud-api/
API Changelog v24.0: https://developers.facebook.com/docs/graph-api/changelog/version24.0
"""

import logging
import time
from typing import Tuple, Optional, Any
import requests
from requests.exceptions import RequestException, Timeout

logger = logging.getLogger(__name__)


class WhatsAppCloudIntegration:
    """
    HTTP Client for Meta Graph API (WhatsApp Cloud API).
    
    Provides low-level HTTP methods (post, get, delete) with:
    - Retry logic with exponential backoff for transient errors
    - Meta API error parsing
    - Sanitized logging (no token exposure)
    
    Usage:
        client = WhatsAppCloudIntegration(access_token="your_token")
        is_error, error_msg, response = client.post("/123456/messages", payload)
    """
    
    API_VERSION = "v24.0"
    BASE_URL = f"https://graph.facebook.com/{API_VERSION}"
    
    # Retry configuration
    MAX_RETRIES = 3
    RETRY_STATUS_CODES = [429, 500, 502, 503, 504]
    INITIAL_BACKOFF = 1  # seconds
    REQUEST_TIMEOUT = 30  # seconds
    
    def __init__(self, access_token: str):
        """
        Initialize the WhatsApp Cloud API client.
        
        Args:
            access_token: Meta Graph API access token from Embedded Signup
        """
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
    
    def post(self, endpoint: str, data: dict) -> Tuple[bool, str, dict]:
        """
        Execute POST request to Meta Graph API.
        
        Args:
            endpoint: API endpoint (e.g., "/{phone_number_id}/messages")
            data: JSON payload to send
            
        Returns:
            Tuple[is_error, error_message, response_dict]
        """
        return self._request("POST", endpoint, json_data=data)
    
    def get(self, endpoint: str, params: dict = None) -> Tuple[bool, str, dict]:
        """
        Execute GET request to Meta Graph API.
        
        Args:
            endpoint: API endpoint (e.g., "/{waba_id}/message_templates")
            params: Query parameters
            
        Returns:
            Tuple[is_error, error_message, response_dict]
        """
        return self._request("GET", endpoint, params=params)
    
    def delete(self, endpoint: str, params: dict = None) -> Tuple[bool, str, dict]:
        """
        Execute DELETE request to Meta Graph API.
        
        Args:
            endpoint: API endpoint (e.g., "/{waba_id}/message_templates")
            params: Query parameters (e.g., {"name": "template_name"})
            
        Returns:
            Tuple[is_error, error_message, response_dict]
        """
        return self._request("DELETE", endpoint, params=params)
    
    def _request(
        self,
        method: str,
        endpoint: str,
        json_data: dict = None,
        params: dict = None
    ) -> Tuple[bool, str, dict]:
        """
        Execute HTTP request with retry logic and exponential backoff.
        
        Args:
            method: HTTP method (GET, POST, DELETE)
            endpoint: API endpoint
            json_data: JSON payload for POST requests
            params: Query parameters for GET/DELETE requests
            
        Returns:
            Tuple[is_error, error_message, response_dict]
        """
        url = f"{self.BASE_URL}{endpoint}"
        
        for attempt in range(self.MAX_RETRIES):
            try:
                self._log_request(method, url, attempt)
                
                response = requests.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    json=json_data,
                    params=params,
                    timeout=self.REQUEST_TIMEOUT
                )
                
                self._log_response(method, url, response.status_code)
                
                # Check if we should retry
                if response.status_code in self.RETRY_STATUS_CODES:
                    if attempt < self.MAX_RETRIES - 1:
                        backoff = self._calculate_backoff(attempt, response)
                        logger.warning(
                            f"Retryable error {response.status_code}, "
                            f"attempt {attempt + 1}/{self.MAX_RETRIES}, "
                            f"waiting {backoff}s"
                        )
                        time.sleep(backoff)
                        continue
                
                return self._validate_response(response)
                
            except Timeout:
                if attempt < self.MAX_RETRIES - 1:
                    backoff = self._calculate_backoff(attempt)
                    logger.warning(
                        f"Request timeout, attempt {attempt + 1}/{self.MAX_RETRIES}, "
                        f"waiting {backoff}s"
                    )
                    time.sleep(backoff)
                    continue
                return True, "Request timeout after all retries", {}
                
            except RequestException as e:
                logger.error(f"Request exception: {str(e)}")
                return True, f"Request failed: {str(e)}", {}
        
        return True, "Max retries exceeded", {}
    
    def _validate_response(self, response: requests.Response) -> Tuple[bool, str, dict]:
        """
        Validate and parse the API response.
        
        Args:
            response: requests.Response object
            
        Returns:
            Tuple[is_error, error_message, response_dict]
        """
        try:
            response_json = response.json()
        except ValueError:
            if response.ok:
                return False, "", {"raw_response": response.text}
            return True, "Invalid JSON response", {"raw_response": response.text}
        
        # Check for Meta API error structure
        if "error" in response_json:
            error_msg = self._parse_error(response_json["error"])
            logger.error(f"Meta API Error: {error_msg}")
            return True, error_msg, response_json
        
        if not response.ok:
            return True, f"HTTP {response.status_code}: {response.text}", response_json
        
        return False, "", response_json
    
    def _parse_error(self, error: dict) -> str:
        """
        Parse Meta API error response into a readable message.
        
        Meta API error structure:
        {
            "error": {
                "message": "...",
                "type": "OAuthException",
                "code": 190,
                "error_subcode": 463,
                "error_user_title": "...",
                "error_user_msg": "...",
                "fbtrace_id": "..."
            }
        }
        
        Args:
            error: Error dict from Meta API response
            
        Returns:
            Formatted error message string
        """
        # Prefer user-friendly messages from Meta if available
        user_title = error.get("error_user_title", "")
        user_msg = error.get("error_user_msg", "")
        
        if user_title and user_msg:
            return f"{user_title}: {user_msg}"
        elif user_msg:
            return user_msg
        
        # Fallback to technical error details
        message = error.get("message", "Unknown error")
        error_type = error.get("type", "")
        code = error.get("code", "")
        subcode = error.get("error_subcode", "")
        
        error_parts = [message]
        
        if code:
            error_parts.append(f"Code: {code}")
        if subcode:
            error_parts.append(f"Subcode: {subcode}")
        if error_type:
            error_parts.append(f"Type: {error_type}")
        
        return " | ".join(error_parts)
    
    def _calculate_backoff(
        self,
        attempt: int,
        response: requests.Response = None
    ) -> float:
        """
        Calculate exponential backoff delay.
        
        For rate limits (429), respects Retry-After header if present.
        
        Args:
            attempt: Current retry attempt number (0-indexed)
            response: Optional response to check for Retry-After header
            
        Returns:
            Backoff delay in seconds
        """
        # Check for Retry-After header on rate limit responses
        if response is not None and response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return float(retry_after)
                except ValueError:
                    pass
        
        # Exponential backoff: 1s, 2s, 4s, ...
        return self.INITIAL_BACKOFF * (2 ** attempt)
    
    def _log_request(self, method: str, url: str, attempt: int) -> None:
        """Log outgoing request with sanitized token."""
        logger.info(
            f"WhatsApp Cloud API Request: {method} {url} "
            f"(attempt {attempt + 1}/{self.MAX_RETRIES}) "
            f"[Auth: Bearer ...{self._sanitize_token()}]"
        )
    
    def _log_response(self, method: str, url: str, status_code: int) -> None:
        """Log API response."""
        log_level = logging.INFO if status_code < 400 else logging.WARNING
        logger.log(
            log_level,
            f"WhatsApp Cloud API Response: {method} {url} -> {status_code}"
        )
    
    def _sanitize_token(self) -> str:
        """
        Return last 4 characters of token for logging.
        
        Returns:
            Sanitized token string (last 4 chars)
        """
        if self.access_token and len(self.access_token) > 4:
            return self.access_token[-4:]
        return "****"
