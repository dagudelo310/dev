# -*- coding:utf-8 -*-
"""
Send Template Message Service

Service for sending WhatsApp messages using approved templates via Meta Graph API.
Endpoint: POST /{phone_number_id}/messages

Reference: https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-message-templates
"""

import logging
from typing import Tuple

from api.integrations.whatsapp_cloud import WhatsAppCloudIntegration
from api.utils import build_template_components

logger = logging.getLogger(__name__)


class SendTemplateMessageService:
    """
    Service for sending WhatsApp messages using approved templates.
    
    WhatsApp Cloud API only allows sending messages via pre-approved templates
    for business-initiated conversations (outside 24h customer service window).
    
    Usage:
        service = SendTemplateMessageService(access_token=line.access_token)
        is_error, error_msg, response = service.execute(
            phone_number_id=line.phone_number_id,
            to="573001234567",
            template_name="poliza_por_vencer",
            language="es",
            params={"1": "Juan", "2": "POL-123", "3": "15/02/2026"}
        )
    """
    
    def __init__(self, access_token: str):
        """
        Initialize the service with Meta Graph API access token.
        
        Args:
            access_token: Meta Graph API access token from CoexistenceLine
        """
        self.client = WhatsAppCloudIntegration(access_token)
    
    def execute(
        self,
        phone_number_id: str,
        to: str,
        template_name: str,
        language: str = "es",
        params: dict = None
    ) -> Tuple[bool, str, dict]:
        """
        Send a WhatsApp message using an approved template.
        
        Args:
            phone_number_id: Meta phone number ID (from CoexistenceLine.phone_number_id)
            to: Recipient phone number in international format (e.g., "573001234567")
            template_name: Name of the approved template in Meta
            language: Template language code (default: "es")
            params: Dict with template variables {"1": "value1", "2": "value2", ...}
                   Variables are ordered by numeric key and inserted into template body
        
        Returns:
            Tuple[is_error, error_message, response]:
                - is_error (bool): True if request failed
                - error_message (str): Error description if failed, empty string otherwise
                - response (dict): Meta API response containing message_id on success
                
        Example response on success:
            {
                "messaging_product": "whatsapp",
                "contacts": [{"input": "573001234567", "wa_id": "573001234567"}],
                "messages": [{"id": "wamid.xxx"}]
            }
        """
        # Build template components from params dict
        components = build_template_components(params) if params else []
        
        endpoint = f"/{phone_number_id}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": components
            }
        }
        
        logger.info(
            f"Sending template message: template={template_name}, "
            f"to={to}, language={language}, params_count={len(params) if params else 0}"
        )
        
        is_error, error_msg, response = self.client.post(endpoint, payload)
        
        if is_error:
            logger.error(
                f"Failed to send template message: {error_msg} | "
                f"template={template_name}, to={to}"
            )
        else:
            message_id = self._extract_message_id(response)
            logger.info(
                f"Template message sent successfully: message_id={message_id}, "
                f"template={template_name}, to={to}"
            )
        
        return is_error, error_msg, response
    
    def _extract_message_id(self, response: dict) -> str:
        """
        Extract message ID from successful response.
        
        Args:
            response: Meta API response dict
            
        Returns:
            Message ID string or "unknown" if not found
        """
        try:
            messages = response.get("messages", [])
            if messages:
                return messages[0].get("id", "unknown")
        except (IndexError, KeyError, TypeError):
            pass
        return "unknown"
