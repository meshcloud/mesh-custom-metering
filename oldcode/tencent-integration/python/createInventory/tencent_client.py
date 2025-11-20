import logging
from dataclasses import dataclass, asdict
from typing import Dict, Optional
import traceback

from tencentcloud.common.credential import Credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.organization.v20210331.organization_client import OrganizationClient
from tencentcloud.organization.v20210331.models import (
    DescribeOrganizationMembersRequest,
)
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException

@dataclass
class TencentAccount:
    """Data class representing a Tencent account"""
    #member_uin: str  # Account ID
    Name: str      # Account display name
    NodeId: str    # Tencent OU ID (landing zone)
    NodeName: str  # Tencent OU display name

    def to_dict(self) -> Dict:
        """Convert TencentAccount instance to dictionary"""
        return asdict(self)

@dataclass
class APIResponse:
    """Data class representing an API response"""
    status: str
    result: Optional[Dict] = None
    message: Optional[str] = None
    total_count: Optional[int] = None

class TencentOrgClient:
    """Client for interacting with Tencent Organization API"""

    DEFAULT_REGION = "ap-guangzhou"
    DEFAULT_ENDPOINT = "organization.tencentcloudapi.com"
    DEFAULT_LANGUAGE = "en"
    DEFAULT_PAGE_SIZE = 50

    def __init__(
        self,
        secret_id: str,
        secret_key: str,
        region: str = DEFAULT_REGION,
        endpoint: str = DEFAULT_ENDPOINT
    ):
        """
        Initialize the Tencent Organization client.

        Args:
            secret_id: Tencent cloud API secret ID
            secret_key: Tencent cloud API secret key
            region: Tencent cloud region (default: ap-guangzhou)
            endpoint: API endpoint (default: organization.tencentcloudapi.com)
        """
        self.credential = Credential(secret_id, secret_key)
        self.region = region
        
        # Setup HTTP profile
        http_profile = HttpProfile()
        http_profile.endpoint = endpoint
        
        # Setup client profile
        self.client_profile = ClientProfile()
        self.client_profile.httpProfile = http_profile
        
        # Initialize the client
        self.client = OrganizationClient(
            credential=self.credential,
            region=self.region,
            profile=self.client_profile
        )

    def _create_request(
        self,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
        lang: str = DEFAULT_LANGUAGE
    ) -> DescribeOrganizationMembersRequest:
        """
        Create a request object for the DescribeOrganizationMembers API.

        Args:
            limit: Maximum number of results per page
            offset: Starting offset for pagination
            lang: Response language (default: en)

        Returns:
            DescribeOrganizationMembersRequest object
        """
        req = DescribeOrganizationMembersRequest()
        req.Limit = limit
        req.Offset = offset
        req.Lang = lang
        return req

    def _process_members(self, members) -> Dict[str, TencentAccount]:
        """
        Process member objects into TencentAccount instances.

        Args:
            members: List of member objects from API response

        Returns:
            Dictionary of TencentAccount objects keyed by member_uin
        """
        return {
            str(member.MemberUin): TencentAccount(
               # member_uin=str(member.MemberUin),
                Name=member.Name,
                NodeId=str(member.NodeId),
                NodeName=member.NodeName
            )
            for member in members
        }

    def _fetch_page(
        self,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
        lang: str = DEFAULT_LANGUAGE
    ) -> Optional[Dict]:
        """
        Fetch a single page of results from the API.

        Args:
            limit: Maximum number of results per page
            offset: Starting offset for pagination
            lang: Response language

        Returns:
            API response dictionary or None if request failed
        """
        try:
            req = self._create_request(limit, offset, lang)
            response = self.client.DescribeOrganizationMembers(req)
            return {
                'items': response.Items,
                'total_count': response.Total
            }
        except TencentCloudSDKException as e:
            error_msg = f"Tencent API Error on page {offset//limit}: {str(e)}"
            logging.error(f"{error_msg}\n{traceback.format_exc()}")
            raise
        except Exception as e:
            error_msg = f"Unexpected error on page {offset//limit}: {str(e)}"
            logging.error(f"{error_msg}\n{traceback.format_exc()}")
            raise

    @staticmethod
    def convert_accounts_to_dict(accounts: Dict[str, TencentAccount]) -> Dict[str, Dict]:
        """
        Convert TencentAccount objects to plain dictionaries.

        Args:
            accounts: Dictionary of TencentAccount objects

        Returns:
            Dictionary of account data as plain dictionaries
        """
        return {
            member_uin: account.to_dict()
            for member_uin, account in accounts.items()
        }

    def retrieve_accounts(
        self,
        page_size: int = DEFAULT_PAGE_SIZE,
        lang: str = DEFAULT_LANGUAGE
    ) -> APIResponse:
        """
        Retrieve all Tencent organization accounts using pagination.

        Args:
            page_size: Number of results per page
            lang: Response language (default: en)

        Returns:
            APIResponse containing dictionary of all TencentAccount objects keyed by member_uin
            and total count of accounts
        """
        try:
            all_accounts = {}
            offset = 0
            total_count = None

            while True:
                # Fetch current page
                logging.info(f"Fetching page with offset {offset}")
                page_data = self._fetch_page(page_size, offset, lang)
                
                if total_count is None:
                    total_count = page_data['total_count']

                # Process current page results
                current_accounts = self._process_members(page_data['items'])
                all_accounts.update(current_accounts)
                
                # Check if we've retrieved all accounts
                if len(all_accounts) >= total_count:
                    break
                
                # Prepare for next page
                offset += page_size

            logging.info(f"Retrieved {len(all_accounts)} Tencent accounts.")
            return APIResponse(
                status="success",
                result=all_accounts,
                total_count=total_count
            )

        except TencentCloudSDKException as e:
            error_msg = f"Tencent API Error: {str(e)}"
            logging.error(f"{error_msg}\n{traceback.format_exc()}")
            return APIResponse(status="failure", message=error_msg)
            
        except Exception as e:
            error_msg = f"Unexpected error while retrieving Tencent accounts: {str(e)}"
            logging.error(f"{error_msg}\n{traceback.format_exc()}")
            return APIResponse(status="failure", message=error_msg)