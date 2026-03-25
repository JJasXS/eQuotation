"""Customer business logic service."""
from typing import Optional, Dict, Any, List, TYPE_CHECKING

if TYPE_CHECKING:
    from api.models import CustomerRequest, CustomerResponse
    from api.adapters import SQLAccountAdapter


class CustomerService:
    """Service layer for customer operations."""
    
    def __init__(self, sql_account_adapter: Optional['SQLAccountAdapter'] = None):
        """
        Initialize the customer service.
        
        Args:
            sql_account_adapter: Optional SQL Account adapter instance
        """
        if sql_account_adapter is None:
            from api.adapters import SQLAccountAdapter
            sql_account_adapter = SQLAccountAdapter()
        self.adapter = sql_account_adapter
    
    def create_customer(self, customer_request: 'CustomerRequest') -> 'CustomerResponse':
        """
        Create a new customer.
        
        Args:
            customer_request: Customer data from API request
            
        Returns:
            Created customer response
            
        Raises:
            ValueError: If validation fails
            Exception: If SQL Account operation fails
        """
        from api.models import CustomerResponse
        
        # Validate required fields
        if not customer_request.companyName:
            raise ValueError("Company name is required")
        if not customer_request.email:
            raise ValueError("Email is required")
        if not customer_request.phone1:
            raise ValueError("Phone number is required")
        if not customer_request.address1:
            raise ValueError("Address is required")
        
        # Prepare data for adapter
        data = customer_request.dict()
        
        # Call SQL Account adapter to create customer
        # (This will be implemented when adapter methods are ready)
        # result = self.adapter.create_customer(data)
        
        # For now, return placeholder response
        response = CustomerResponse(
            customerCode=customer_request.customerCode or "TBD",
            companyName=customer_request.companyName,
            phone1=customer_request.phone1,
            email=customer_request.email,
            address1=customer_request.address1,
            address2=customer_request.address2,
            address3=customer_request.address3,
            address4=customer_request.address4,
            postcode=customer_request.postcode,
            city=customer_request.city,
            state=customer_request.state,
            country=customer_request.country,
        )
        return response
    
    def get_customer(self, customer_code: str) -> Optional['CustomerResponse']:
        """
        Retrieve customer by code.
        
        Args:
            customer_code: Customer code to retrieve
            
        Returns:
            Customer data or None if not found
        """
        # Call SQL Account adapter
        # data = self.adapter.get_customer(customer_code)
        # if data:
        #     return CustomerResponse(**data)
        
        # Placeholder for testing
        return None
    
    def update_customer(self, customer_code: str, customer_request: 'CustomerRequest') -> 'CustomerResponse':
        """
        Update an existing customer.
        
        Args:
            customer_code: Customer code to update
            customer_request: Updated customer data
            
        Returns:
            Updated customer response
            
        Raises:
            ValueError: If customer not found or validation fails
        """
        from api.models import CustomerResponse
        
        # Validate that customer exists
        existing = self.get_customer(customer_code)
        if not existing:
            raise ValueError(f"Customer {customer_code} not found")
        
        # Validate required fields
        if not customer_request.companyName:
            raise ValueError("Company name is required")
        
        # Call SQL Account adapter to update
        # self.adapter.update_customer(customer_code, customer_request.dict())
        
        # Return updated response
        response = CustomerResponse(
            customerCode=customer_code,
            companyName=customer_request.companyName,
            phone1=customer_request.phone1,
            email=customer_request.email,
            address1=customer_request.address1,
            address2=customer_request.address2,
            address3=customer_request.address3,
            address4=customer_request.address4,
            postcode=customer_request.postcode,
            city=customer_request.city,
            state=customer_request.state,
            country=customer_request.country,
        )
        return response
    
    def delete_customer(self, customer_code: str) -> bool:
        """
        Delete a customer.
        
        Args:
            customer_code: Customer code to delete
            
        Returns:
            True if successful
            
        Raises:
            ValueError: If customer not found
        """
        existing = self.get_customer(customer_code)
        if not existing:
            raise ValueError(f"Customer {customer_code} not found")
        
        # Call SQL Account adapter
        # return self.adapter.delete_customer(customer_code)
        return True
