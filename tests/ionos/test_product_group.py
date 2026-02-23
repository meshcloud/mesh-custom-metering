import sys
import pytest
import base64
from unittest.mock import Mock, patch, MagicMock
import requests

# Add the platform directory to the path for imports
sys.path.insert(0, '/Users/youngi/git-repos/mesh-custom-metering/platforms/ionos')
sys.path.insert(0, '/Users/youngi/git-repos/mesh-custom-metering/src/core')


@pytest.fixture
def sample_products():
    """Sample IONOS products with product groups."""
    return {
        'products': [
            {
                'meterId': 'compute-1',
                'meterDesc': 'VM Instance',
                'unitCost': {'quantity': 10.50},
                'productGroup': 'Compute'
            },
            {
                'meterId': 'storage-1',
                'meterDesc': 'Storage',
                'unitCost': {'quantity': 5.00},
                'productGroup': 'Storage'
            },
            {
                'meterId': 'network-1',
                'meterDesc': 'Bandwidth',
                'unitCost': {'quantity': 2.50},
                'productGroup': 'Network'
            },
            {
                'meterId': 'unknown-1',
                'meterDesc': 'Unknown Service',
                'unitCost': {'quantity': 1.00}
                # No productGroup field for this one
            }
        ]
    }


@pytest.fixture
def sample_usage():
    """Sample IONOS usage data."""
    return {
        'datacenters': [
            {
                'id': 'de-1',
                'name': 'Germany 1',
                'meters': [
                    {
                        'meterId': 'vm-123',
                        'meterDesc': 'VM Instance',
                        'quantity': {'quantity': 5, 'unit': 'hours'}
                    },
                    {
                        'meterId': 'storage-123',
                        'meterDesc': 'Storage',
                        'quantity': {'quantity': 100, 'unit': 'GB'}
                    },
                    {
                        'meterId': 'bandwidth-123',
                        'meterDesc': 'Bandwidth',
                        'quantity': {'quantity': 50, 'unit': 'GB'}
                    }
                ]
            }
        ]
    }


# ============================================================================
# AUTHENTICATION TESTS
# ============================================================================

class TestIonosAuthentication:
    """Tests for IONOS authentication functionality."""
    
    def test_create_ionos_auth_headers_success(self):
        """Test successful creation of Basic Auth header."""
        from main import create_ionos_auth_headers
        
        with patch.dict('os.environ', {
            'IONOS_USERNAME': 'user@example.com',
            'IONOS_PASSWORD': 'password123'
        }):
            headers = create_ionos_auth_headers()
            
            assert 'Authorization' in headers
            assert headers['Authorization'].startswith('Basic ')
            assert 'Accept' in headers
            assert headers['Accept'] == 'application/json'
    
    def test_auth_header_base64_encoding_correct(self):
        """Test that credentials are correctly Base64 encoded."""
        from main import create_ionos_auth_headers
        
        username = 'user@example.com'
        password = 'password123'
        
        with patch.dict('os.environ', {
            'IONOS_USERNAME': username,
            'IONOS_PASSWORD': password
        }):
            headers = create_ionos_auth_headers()
            
            # Extract the Base64 part
            auth_header = headers['Authorization']
            assert auth_header.startswith('Basic ')
            encoded_part = auth_header.replace('Basic ', '')
            
            # Decode and verify
            decoded = base64.b64decode(encoded_part).decode('utf-8')
            assert decoded == f"{username}:{password}"
    
    def test_create_ionos_auth_headers_missing_username(self):
        """Test that missing username raises ValueError."""
        from main import create_ionos_auth_headers
        
        with patch.dict('os.environ', {
            'IONOS_PASSWORD': 'password123'
        }, clear=False):
            # Remove IONOS_USERNAME if it exists
            if 'IONOS_USERNAME' in dict(globals()):
                del globals()['IONOS_USERNAME']
            
            with pytest.raises(ValueError, match="IONOS_USERNAME"):
                create_ionos_auth_headers()
    
    def test_create_ionos_auth_headers_missing_password(self):
        """Test that missing password raises ValueError."""
        from main import create_ionos_auth_headers
        
        with patch.dict('os.environ', {
            'IONOS_USERNAME': 'user@example.com'
        }, clear=False):
            with pytest.raises(ValueError, match="IONOS_PASSWORD"):
                create_ionos_auth_headers()
    
    def test_create_ionos_auth_headers_empty_username(self):
        """Test that empty username raises ValueError."""
        from main import create_ionos_auth_headers
        
        with patch.dict('os.environ', {
            'IONOS_USERNAME': '',
            'IONOS_PASSWORD': 'password123'
        }):
            with pytest.raises(ValueError, match="IONOS_USERNAME"):
                create_ionos_auth_headers()
    
    def test_create_ionos_auth_headers_whitespace_only(self):
        """Test that whitespace-only credentials are treated as empty."""
        from main import create_ionos_auth_headers
        
        with patch.dict('os.environ', {
            'IONOS_USERNAME': '   ',
            'IONOS_PASSWORD': 'password123'
        }):
            with pytest.raises(ValueError, match="IONOS_USERNAME"):
                create_ionos_auth_headers()


class TestIonosCredentialValidation:
    """Tests for IONOS credential validation."""
    
    def test_validate_ionos_credentials_success(self):
        """Test successful credential validation."""
        from main import validate_ionos_credentials
        
        with patch.dict('os.environ', {
            'IONOS_USERNAME': 'user@example.com',
            'IONOS_PASSWORD': 'password123',
            'IONOS_CONTRACT': 'contract123'
        }):
            # Should not raise
            validate_ionos_credentials()
    
    def test_validate_ionos_credentials_missing_username(self):
        """Test validation fails with missing username."""
        from main import validate_ionos_credentials
        
        with patch.dict('os.environ', {
            'IONOS_PASSWORD': 'password123',
            'IONOS_CONTRACT': 'contract123'
        }, clear=False):
            with pytest.raises(ValueError, match="IONOS_USERNAME"):
                validate_ionos_credentials()
    
    def test_validate_ionos_credentials_missing_password(self):
        """Test validation fails with missing password."""
        from main import validate_ionos_credentials
        
        with patch.dict('os.environ', {
            'IONOS_USERNAME': 'user@example.com',
            'IONOS_CONTRACT': 'contract123'
        }, clear=False):
            with pytest.raises(ValueError, match="IONOS_PASSWORD"):
                validate_ionos_credentials()
    
    def test_validate_ionos_credentials_missing_contract(self):
        """Test validation fails with missing contract."""
        from main import validate_ionos_credentials
        
        with patch.dict('os.environ', {
            'IONOS_USERNAME': 'user@example.com',
            'IONOS_PASSWORD': 'password123'
        }, clear=False):
            with pytest.raises(ValueError, match="IONOS_CONTRACT"):
                validate_ionos_credentials()
    
    def test_validate_ionos_credentials_multiple_missing(self):
        """Test validation message includes all missing variables."""
        from main import validate_ionos_credentials
        
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                validate_ionos_credentials()
            
            error_msg = str(exc_info.value)
            assert "IONOS_USERNAME" in error_msg
            assert "IONOS_PASSWORD" in error_msg
            assert "IONOS_CONTRACT" in error_msg


class TestIonosSession:
    """Tests for IONOS session creation with retry strategy."""
    
    def test_create_ionos_session_success(self):
        """Test successful session creation."""
        from main import create_ionos_session
        
        session = create_ionos_session(timeout=30, max_retries=3)
        
        assert isinstance(session, requests.Session)
        assert session is not None
        
        # Verify adapter is mounted
        assert 'http://' in session.adapters
        assert 'https://' in session.adapters
    
    def test_create_ionos_session_with_custom_timeout(self):
        """Test session creation with custom timeout."""
        from main import create_ionos_session
        
        session = create_ionos_session(timeout=60, max_retries=5)
        
        assert isinstance(session, requests.Session)
        # Timeout is stored as an attribute
        # (Note: requests.Session doesn't natively store timeout, but we added it)
    
    def test_create_ionos_session_default_values(self):
        """Test session creation uses default values."""
        from main import create_ionos_session
        
        session = create_ionos_session()
        
        assert isinstance(session, requests.Session)


class TestProductGroupFeature:
    """Tests for product group functionality (existing tests)."""
    
    def test_without_product_group(self, sample_usage, sample_products):
        """Test that costs are calculated correctly without product group."""
        from main import calculate_datacenter_costs
        
        result = calculate_datacenter_costs(sample_usage, sample_products, include_product_group=False)
        
        assert len(result) == 1
        datacenter = result[0]
        assert datacenter['id'] == 'de-1'
        assert datacenter['name'] == 'Germany 1'
        assert len(datacenter['meters']) == 3
        
        # Check first meter (VM)
        vm_meter = datacenter['meters'][0]
        assert vm_meter['meterId'] == 'vm-123'
        assert vm_meter['meterDesc'] == 'VM Instance'
        assert vm_meter['quantity'] == 5
        assert vm_meter['unit'] == 'hours'
        assert vm_meter['totalCost'] == 52.50  # 5 * 10.50
        assert 'productGroup' not in vm_meter
    
    def test_with_product_group(self, sample_usage, sample_products):
        """Test that product groups are included when enabled."""
        from main import calculate_datacenter_costs
        
        result = calculate_datacenter_costs(sample_usage, sample_products, include_product_group=True)
        
        datacenter = result[0]
        
        # Check first meter (VM) includes product group
        vm_meter = datacenter['meters'][0]
        assert 'productGroup' in vm_meter
        assert vm_meter['productGroup'] == 'Compute'
        
        # Check second meter (Storage) includes product group
        storage_meter = datacenter['meters'][1]
        assert 'productGroup' in storage_meter
        assert storage_meter['productGroup'] == 'Storage'
        
        # Check third meter (Bandwidth) includes product group
        bandwidth_meter = datacenter['meters'][2]
        assert 'productGroup' in bandwidth_meter
        assert bandwidth_meter['productGroup'] == 'Network'
    
    def test_product_group_missing_gracefully_handled(self):
        """Test that missing product group doesn't cause errors."""
        from main import calculate_datacenter_costs
        
        products = {
            'products': [
                {
                    'meterId': 'service-1',
                    'meterDesc': 'Service',
                    'unitCost': {'quantity': 1.00}
                    # No productGroup field
                }
            ]
        }
        
        usage = {
            'datacenters': [
                {
                    'id': 'dc-1',
                    'name': 'DC 1',
                    'meters': [
                        {
                            'meterId': 'meter-1',
                            'meterDesc': 'Service',
                            'quantity': {'quantity': 10, 'unit': 'units'}
                        }
                    ]
                }
            ]
        }
        
        result = calculate_datacenter_costs(usage, products, include_product_group=True)
        
        datacenter = result[0]
        meter = datacenter['meters'][0]
        # Product group should not be added if it's missing
        assert 'productGroup' not in meter
    
    def test_cost_calculation_accuracy(self, sample_usage, sample_products):
        """Test that cost calculations are accurate."""
        from main import calculate_datacenter_costs
        
        result = calculate_datacenter_costs(sample_usage, sample_products, include_product_group=False)
        meters = result[0]['meters']
        
        # VM: 5 hours * €10.50 = €52.50
        assert meters[0]['totalCost'] == 52.50
        
        # Storage: 100 GB * €5.00 = €500.00
        assert meters[1]['totalCost'] == 500.00
        
        # Bandwidth: 50 GB * €2.50 = €125.00
        assert meters[2]['totalCost'] == 125.00


class TestTransformIonosToLineItems:
    """Tests for line item transformation."""
    
    def test_line_items_without_product_group(self, sample_products):
        """Test line item transformation without product group."""
        from main import transform_ionos_to_line_items
        
        meters = [
            {
                'meterId': 'vm-123',
                'meterDesc': 'VM Instance',
                'quantity': 5,
                'unit': 'hours',
                'totalCost': 52.50,
                'unitCost': 10.50
            }
        ]
        
        line_items = transform_ionos_to_line_items(meters, include_product_group=False)
        
        assert len(line_items) == 1
        item = line_items[0]
        assert item['productName'] == 'VM Instance'
        assert item['usageQuantity'] == 5
        assert item['usageType'] == 'IONOS Service vm-123'
        assert item['usageCost'] == 52.50
        assert item['currency'] == 'EUR'
        assert item['usageUnit'] == 'hours'
        assert item['totalCost'] == 52.50
        assert item['sellerId'] == 'IONOS'
        assert 'productGroup' not in item
    
    def test_line_items_with_product_group(self):
        """Test line item transformation with product group."""
        from main import transform_ionos_to_line_items
        
        meters = [
            {
                'meterId': 'vm-123',
                'meterDesc': 'VM Instance',
                'quantity': 5,
                'unit': 'hours',
                'totalCost': 52.50,
                'unitCost': 10.50,
                'productGroup': 'Compute'
            },
            {
                'meterId': 'storage-123',
                'meterDesc': 'Storage',
                'quantity': 100,
                'unit': 'GB',
                'totalCost': 500.00,
                'unitCost': 5.00,
                'productGroup': 'Storage'
            }
        ]
        
        line_items = transform_ionos_to_line_items(meters, include_product_group=True)
        
        assert len(line_items) == 2
        
        # First item should have product group
        assert line_items[0]['productGroup'] == 'Compute'
        
        # Second item should have product group
        assert line_items[1]['productGroup'] == 'Storage'
    
    def test_zero_cost_items_excluded(self):
        """Test that items with zero cost are excluded."""
        from main import transform_ionos_to_line_items
        
        meters = [
            {
                'meterId': 'vm-123',
                'meterDesc': 'VM Instance',
                'quantity': 5,
                'unit': 'hours',
                'totalCost': 52.50,
                'unitCost': 10.50
            },
            {
                'meterId': 'free-service',
                'meterDesc': 'Free Service',
                'quantity': 100,
                'unit': 'units',
                'totalCost': 0,
                'unitCost': 0
            }
        ]
        
        line_items = transform_ionos_to_line_items(meters, include_product_group=False)
        
        # Only the paid service should be included
        assert len(line_items) == 1
        assert line_items[0]['productName'] == 'VM Instance'
    
    def test_product_group_only_included_when_present(self):
        """Test that product group is only included when present in meter."""
        from main import transform_ionos_to_line_items
        
        meters = [
            {
                'meterId': 'service-1',
                'meterDesc': 'Service',
                'quantity': 10,
                'unit': 'units',
                'totalCost': 100.00,
                'unitCost': 10.00,
                'productGroup': 'Compute'
            },
            {
                'meterId': 'service-2',
                'meterDesc': 'Service 2',
                'quantity': 20,
                'unit': 'units',
                'totalCost': 200.00,
                'unitCost': 10.00
                # No productGroup
            }
        ]
        
        line_items = transform_ionos_to_line_items(meters, include_product_group=True)
        
        assert len(line_items) == 2
        assert 'productGroup' in line_items[0]
        assert 'productGroup' not in line_items[1]


class TestEndToEnd:
    """End-to-end integration tests."""
    
    def test_complete_flow_with_product_group(self, sample_usage, sample_products):
        """Test the complete flow from usage to line items with product group."""
        from main import calculate_datacenter_costs, transform_ionos_to_line_items
        
        # Step 1: Calculate costs with product group
        datacenter_costs = calculate_datacenter_costs(sample_usage, sample_products, include_product_group=True)
        
        # Step 2: Transform to line items
        line_items = transform_ionos_to_line_items(datacenter_costs[0]['meters'], include_product_group=True)
        
        # Verify
        assert len(line_items) == 3
        assert line_items[0]['productGroup'] == 'Compute'
        assert line_items[1]['productGroup'] == 'Storage'
        assert line_items[2]['productGroup'] == 'Network'
        
        # All required fields present
        for item in line_items:
            assert 'productName' in item
            assert 'usageQuantity' in item
            assert 'usageType' in item
            assert 'usageCost' in item
            assert 'currency' in item
            assert 'usageUnit' in item
            assert 'totalCost' in item
            assert 'sellerId' in item
            assert 'productGroup' in item

    """Tests for calculate_datacenter_costs function."""
    
    def test_without_product_group(self, sample_usage, sample_products):
        """Test that costs are calculated correctly without product group."""
        from main import calculate_datacenter_costs
        
        result = calculate_datacenter_costs(sample_usage, sample_products, include_product_group=False)
        
        assert len(result) == 1
        datacenter = result[0]
        assert datacenter['id'] == 'de-1'
        assert datacenter['name'] == 'Germany 1'
        assert len(datacenter['meters']) == 3
        
        # Check first meter (VM)
        vm_meter = datacenter['meters'][0]
        assert vm_meter['meterId'] == 'vm-123'
        assert vm_meter['meterDesc'] == 'VM Instance'
        assert vm_meter['quantity'] == 5
        assert vm_meter['unit'] == 'hours'
        assert vm_meter['totalCost'] == 52.50  # 5 * 10.50
        assert 'productGroup' not in vm_meter
    
    def test_with_product_group(self, sample_usage, sample_products):
        """Test that product groups are included when enabled."""
        from main import calculate_datacenter_costs
        
        result = calculate_datacenter_costs(sample_usage, sample_products, include_product_group=True)
        
        datacenter = result[0]
        
        # Check first meter (VM) includes product group
        vm_meter = datacenter['meters'][0]
        assert 'productGroup' in vm_meter
        assert vm_meter['productGroup'] == 'Compute'
        
        # Check second meter (Storage) includes product group
        storage_meter = datacenter['meters'][1]
        assert 'productGroup' in storage_meter
        assert storage_meter['productGroup'] == 'Storage'
        
        # Check third meter (Bandwidth) includes product group
        bandwidth_meter = datacenter['meters'][2]
        assert 'productGroup' in bandwidth_meter
        assert bandwidth_meter['productGroup'] == 'Network'
    
    def test_product_group_missing_gracefully_handled(self):
        """Test that missing product group doesn't cause errors."""
        from main import calculate_datacenter_costs
        
        products = {
            'products': [
                {
                    'meterId': 'service-1',
                    'meterDesc': 'Service',
                    'unitCost': {'quantity': 1.00}
                    # No productGroup field
                }
            ]
        }
        
        usage = {
            'datacenters': [
                {
                    'id': 'dc-1',
                    'name': 'DC 1',
                    'meters': [
                        {
                            'meterId': 'meter-1',
                            'meterDesc': 'Service',
                            'quantity': {'quantity': 10, 'unit': 'units'}
                        }
                    ]
                }
            ]
        }
        
        result = calculate_datacenter_costs(usage, products, include_product_group=True)
        
        datacenter = result[0]
        meter = datacenter['meters'][0]
        # Product group should not be added if it's missing
        assert 'productGroup' not in meter
    
    def test_cost_calculation_accuracy(self, sample_usage, sample_products):
        """Test that cost calculations are accurate."""
        from main import calculate_datacenter_costs
        
        result = calculate_datacenter_costs(sample_usage, sample_products, include_product_group=False)
        meters = result[0]['meters']
        
        # VM: 5 hours * €10.50 = €52.50
        assert meters[0]['totalCost'] == 52.50
        
        # Storage: 100 GB * €5.00 = €500.00
        assert meters[1]['totalCost'] == 500.00
        
        # Bandwidth: 50 GB * €2.50 = €125.00
        assert meters[2]['totalCost'] == 125.00


class TestTransformIonosToLineItems:
    """Tests for transform_ionos_to_line_items function."""
    
    def test_line_items_without_product_group(self, sample_products):
        """Test line item transformation without product group."""
        from main import transform_ionos_to_line_items
        
        meters = [
            {
                'meterId': 'vm-123',
                'meterDesc': 'VM Instance',
                'quantity': 5,
                'unit': 'hours',
                'totalCost': 52.50,
                'unitCost': 10.50
            }
        ]
        
        line_items = transform_ionos_to_line_items(meters, include_product_group=False)
        
        assert len(line_items) == 1
        item = line_items[0]
        assert item['productName'] == 'VM Instance'
        assert item['usageQuantity'] == 5
        assert item['usageType'] == 'IONOS Service vm-123'
        assert item['usageCost'] == 52.50
        assert item['currency'] == 'EUR'
        assert item['usageUnit'] == 'hours'
        assert item['totalCost'] == 52.50
        assert item['sellerId'] == 'IONOS'
        assert 'productGroup' not in item
    
    def test_line_items_with_product_group(self):
        """Test line item transformation with product group."""
        from main import transform_ionos_to_line_items
        
        meters = [
            {
                'meterId': 'vm-123',
                'meterDesc': 'VM Instance',
                'quantity': 5,
                'unit': 'hours',
                'totalCost': 52.50,
                'unitCost': 10.50,
                'productGroup': 'Compute'
            },
            {
                'meterId': 'storage-123',
                'meterDesc': 'Storage',
                'quantity': 100,
                'unit': 'GB',
                'totalCost': 500.00,
                'unitCost': 5.00,
                'productGroup': 'Storage'
            }
        ]
        
        line_items = transform_ionos_to_line_items(meters, include_product_group=True)
        
        assert len(line_items) == 2
        
        # First item should have product group
        assert line_items[0]['productGroup'] == 'Compute'
        
        # Second item should have product group
        assert line_items[1]['productGroup'] == 'Storage'
    
    def test_zero_cost_items_excluded(self):
        """Test that items with zero cost are excluded."""
        from main import transform_ionos_to_line_items
        
        meters = [
            {
                'meterId': 'vm-123',
                'meterDesc': 'VM Instance',
                'quantity': 5,
                'unit': 'hours',
                'totalCost': 52.50,
                'unitCost': 10.50
            },
            {
                'meterId': 'free-service',
                'meterDesc': 'Free Service',
                'quantity': 100,
                'unit': 'units',
                'totalCost': 0,
                'unitCost': 0
            }
        ]
        
        line_items = transform_ionos_to_line_items(meters, include_product_group=False)
        
        # Only the paid service should be included
        assert len(line_items) == 1
        assert line_items[0]['productName'] == 'VM Instance'
    
    def test_product_group_only_included_when_present(self):
        """Test that product group is only included when present in meter."""
        from main import transform_ionos_to_line_items
        
        meters = [
            {
                'meterId': 'service-1',
                'meterDesc': 'Service',
                'quantity': 10,
                'unit': 'units',
                'totalCost': 100.00,
                'unitCost': 10.00,
                'productGroup': 'Compute'
            },
            {
                'meterId': 'service-2',
                'meterDesc': 'Service 2',
                'quantity': 20,
                'unit': 'units',
                'totalCost': 200.00,
                'unitCost': 10.00
                # No productGroup
            }
        ]
        
        line_items = transform_ionos_to_line_items(meters, include_product_group=True)
        
        assert len(line_items) == 2
        assert 'productGroup' in line_items[0]
        assert 'productGroup' not in line_items[1]


class TestEndToEnd:
    """End-to-end tests for the complete flow."""
    
    def test_complete_flow_with_product_group(self, sample_usage, sample_products):
        """Test the complete flow from usage to line items with product group."""
        from main import calculate_datacenter_costs, transform_ionos_to_line_items
        
        # Step 1: Calculate costs with product group
        datacenter_costs = calculate_datacenter_costs(sample_usage, sample_products, include_product_group=True)
        
        # Step 2: Transform to line items
        line_items = transform_ionos_to_line_items(datacenter_costs[0]['meters'], include_product_group=True)
        
        # Verify
        assert len(line_items) == 3
        assert line_items[0]['productGroup'] == 'Compute'
        assert line_items[1]['productGroup'] == 'Storage'
        assert line_items[2]['productGroup'] == 'Network'
        
        # All required fields present
        for item in line_items:
            assert 'productName' in item
            assert 'usageQuantity' in item
            assert 'usageType' in item
            assert 'usageCost' in item
            assert 'currency' in item
            assert 'usageUnit' in item
            assert 'totalCost' in item
            assert 'sellerId' in item
            assert 'productGroup' in item
