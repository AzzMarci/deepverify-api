from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
import phonenumbers
from phonenumbers import carrier, geocoder, timezone
import email_validator
import dns.resolver
import re
import requests
import os
from typing import Optional, Dict, List
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Advanced Email & Phone Validation API",
    description="Professional API for validating emails and phone numbers with advanced features",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response Models
class EmailValidationRequest(BaseModel):
    email: str

class EmailValidationResponse(BaseModel):
    valid: bool
    disposable: bool
    domain_exists: bool
    mx_found: bool
    provider: Optional[str]
    suggestion: Optional[str]
    confidence_score: float
    details: Dict

class PhoneValidationRequest(BaseModel):
    phone: str

class PhoneValidationResponse(BaseModel):
    valid: bool
    international_format: Optional[str]
    country: Optional[str]
    country_code: Optional[str]
    type: Optional[str]
    carrier: Optional[str]
    line_type: Optional[str]
    timezone: Optional[List[str]]
    confidence_score: float

class EmailValidator:
    def __init__(self):
        self.disposable_domains = self._load_disposable_domains()
        self.known_providers = {
            'gmail.com': 'Gmail',
            'googlemail.com': 'Gmail',
            'outlook.com': 'Outlook',
            'hotmail.com': 'Hotmail',
            'live.com': 'Microsoft Live',
            'yahoo.com': 'Yahoo',
            'yahoo.it': 'Yahoo Italy',
            'yahoo.co.uk': 'Yahoo UK',
            'protonmail.com': 'ProtonMail',
            'icloud.com': 'iCloud',
            'me.com': 'iCloud',
            'mac.com': 'iCloud',
            'libero.it': 'Libero',
            'tiscali.it': 'Tiscali',
            'alice.it': 'Alice',
            'virgilio.it': 'Virgilio',
            'tin.it': 'TIN'
        }
        self.suspicious_tlds = {'.tk', '.ml', '.ga', '.cf', '.top', '.click', '.download', '.win'}
        
        # Future API integration setup (commented for now)
        # self.external_api_key = os.environ.get('EMAIL_VALIDATION_API_KEY')
        # self.use_external_api = bool(self.external_api_key)
    
    def _load_disposable_domains(self) -> set:
        """Load disposable email domains from static list with fallback"""
        default_disposable = {
            '10minutemail.com', 'guerrillamail.com', 'mailinator.com', 
            'tempmail.org', 'temp-mail.org', 'throwaway.email',
            'maildrop.cc', 'yopmail.com', 'mailnesia.com',
            'mintemail.com', 'mohmal.com', 'dispostable.com'
        }
        
        try:
            # Try to download updated list (this would be done periodically in production)
            # For now, using static list
            logger.info("Using static disposable domains list")
            return default_disposable
        except Exception as e:
            logger.warning(f"Could not update disposable domains: {e}")
            return default_disposable
    
    def _check_domain_exists(self, domain: str) -> bool:
        """Check if domain exists via DNS"""
        try:
            dns.resolver.resolve(domain, 'A')
            return True
        except:
            try:
                dns.resolver.resolve(domain, 'AAAA')
                return True
            except:
                return False
    
    def _check_mx_records(self, domain: str) -> bool:
        """Check if domain has MX records"""
        try:
            mx_records = dns.resolver.resolve(domain, 'MX')
            return len(mx_records) > 0
        except:
            return False
    
    def _is_disposable(self, domain: str) -> bool:
        """Check if domain is disposable using hybrid approach"""
        if domain.lower() in self.disposable_domains:
            return True
        
        # Heuristic checks
        if len(domain) < 4:  # Very short domains are suspicious
            return True
        
        # Check suspicious TLDs
        for tld in self.suspicious_tlds:
            if domain.endswith(tld):
                return True
        
        # Pattern checks for generated domains
        if re.match(r'^[a-z0-9]{10,}\.com$', domain):  # Random string domains
            return True
        
        return False
    
    def _get_provider(self, domain: str) -> Optional[str]:
        """Identify email provider"""
        return self.known_providers.get(domain.lower())
    
    def _calculate_confidence(self, valid: bool, domain_exists: bool, 
                            mx_found: bool, disposable: bool, provider: Optional[str]) -> float:
        """Calculate confidence score based on validation results"""
        score = 0.0
        
        if valid:
            score += 0.4
        if domain_exists:
            score += 0.2
        if mx_found:
            score += 0.2
        if not disposable:
            score += 0.1
        if provider:
            score += 0.1
        
        return round(score, 2)
    
    async def validate(self, email: str) -> EmailValidationResponse:
        """Main email validation function"""
        details = {}
        
        try:
            # Basic format validation
            validated_email = email_validator.validate_email(email)
            domain = validated_email.domain
            valid = True
            details['normalized_email'] = validated_email.email
        except email_validator.EmailNotValidError as e:
            valid = False
            domain = email.split('@')[-1] if '@' in email else ''
            details['validation_error'] = str(e)
        
        # Domain checks
        domain_exists = self._check_domain_exists(domain) if domain else False
        mx_found = self._check_mx_records(domain) if domain_exists else False
        disposable = self._is_disposable(domain) if domain else False
        provider = self._get_provider(domain) if domain else None
        
        # Future external API integration point
        # if self.use_external_api and valid:
        #     external_result = await self._check_external_api(email)
        #     details['external_validation'] = external_result
        
        confidence_score = self._calculate_confidence(valid, domain_exists, mx_found, disposable, provider)
        
        details.update({
            'domain': domain,
            'checks_performed': ['format', 'dns', 'mx', 'disposable', 'provider']
        })
        
        return EmailValidationResponse(
            valid=valid and domain_exists and mx_found and not disposable,
            disposable=disposable,
            domain_exists=domain_exists,
            mx_found=mx_found,
            provider=provider,
            suggestion=None,  # Could implement typo suggestions
            confidence_score=confidence_score,
            details=details
        )

class PhoneValidator:
    def __init__(self):
        pass
    
    def _get_line_type(self, phone_type) -> str:
        """Convert phonenumbers type to readable string"""
        type_mapping = {
            phonenumbers.PhoneNumberType.MOBILE: "mobile",
            phonenumbers.PhoneNumberType.FIXED_LINE: "landline",
            phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "landline_or_mobile",
            phonenumbers.PhoneNumberType.TOLL_FREE: "toll_free",
            phonenumbers.PhoneNumberType.PREMIUM_RATE: "premium_rate",
            phonenumbers.PhoneNumberType.SHARED_COST: "shared_cost",
            phonenumbers.PhoneNumberType.VOIP: "voip",
            phonenumbers.PhoneNumberType.PERSONAL_NUMBER: "personal",
            phonenumbers.PhoneNumberType.PAGER: "pager",
            phonenumbers.PhoneNumberType.UAN: "uan",
            phonenumbers.PhoneNumberType.VOICEMAIL: "voicemail",
            phonenumbers.PhoneNumberType.UNKNOWN: "unknown"
        }
        return type_mapping.get(phone_type, "unknown")
    
    def _calculate_confidence(self, valid: bool, has_carrier: bool, has_location: bool) -> float:
        """Calculate confidence score for phone validation"""
        score = 0.0
        
        if valid:
            score += 0.7
        if has_carrier:
            score += 0.15
        if has_location:
            score += 0.15
        
        return round(score, 2)
    
    def validate(self, phone: str) -> PhoneValidationResponse:
        """Main phone validation function"""
        try:
            # Parse the phone number with more flexible parsing
            # Try without region first, then with common regions if it fails
            try:
                parsed_number = phonenumbers.parse(phone, None)
            except phonenumbers.NumberParseException:
                # Try with US region for numbers that might be missing country code
                try:
                    parsed_number = phonenumbers.parse(phone, "US")
                except phonenumbers.NumberParseException:
                    # Try with IT region as fallback
                    parsed_number = phonenumbers.parse(phone, "IT")
            
            # Check if valid
            is_valid = phonenumbers.is_valid_number(parsed_number)
            
            if not is_valid:
                return PhoneValidationResponse(
                    valid=False,
                    international_format=None,
                    country=None,
                    country_code=None,
                    type=None,
                    carrier=None,
                    line_type=None,
                    timezone=None,
                    confidence_score=0.0
                )
            
            # Get detailed information
            international_format = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
            country = geocoder.description_for_number(parsed_number, "en")
            country_code = phonenumbers.region_code_for_number(parsed_number)
            phone_type = phonenumbers.number_type(parsed_number)
            line_type = self._get_line_type(phone_type)
            
            # Get carrier info (may not always be available)
            try:
                carrier_name = carrier.name_for_number(parsed_number, "en")
            except:
                carrier_name = None
            
            # Get timezone info
            try:
                timezones = timezone.time_zones_for_number(parsed_number)
            except:
                timezones = None
            
            confidence_score = self._calculate_confidence(
                is_valid, 
                bool(carrier_name), 
                bool(country)
            )
            
            return PhoneValidationResponse(
                valid=True,
                international_format=international_format,
                country=country or None,
                country_code=country_code,
                type=line_type,
                carrier=carrier_name or None,
                line_type=line_type,
                timezone=list(timezones) if timezones else None,
                confidence_score=confidence_score
            )
            
        except phonenumbers.NumberParseException as e:
            return PhoneValidationResponse(
                valid=False,
                international_format=None,
                country=None,
                country_code=None,
                type=None,
                carrier=None,
                line_type=None,
                timezone=None,
                confidence_score=0.0
            )

# Initialize validators
email_validator_instance = EmailValidator()
phone_validator_instance = PhoneValidator()

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Advanced Email & Phone Validation API",
        "version": "1.0.0",
        "endpoints": ["/api/validate/email", "/api/validate/phone"],
        "documentation": "/docs",
        "status": "active"
    }

@app.post("/api/validate/email", response_model=EmailValidationResponse)
async def validate_email(request: EmailValidationRequest):
    """
    Validate email address with advanced checks:
    - RFC format compliance
    - Domain existence (DNS)
    - MX record verification
    - Disposable email detection
    - Provider identification
    """
    try:
        result = await email_validator_instance.validate(request.email)
        return result
    except Exception as e:
        logger.error(f"Email validation error: {e}")
        raise HTTPException(status_code=500, detail="Internal validation error")

@app.post("/api/validate/phone", response_model=PhoneValidationResponse)
async def validate_phone(request: PhoneValidationRequest):
    """
    Validate phone number with detailed information:
    - International format (E.164)
    - Country and region
    - Line type (mobile/landline/VoIP)
    - Carrier information
    - Timezone data
    """
    try:
        result = phone_validator_instance.validate(request.phone)
        return result
    except Exception as e:
        logger.error(f"Phone validation error: {e}")
        raise HTTPException(status_code=500, detail="Internal validation error")

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "message": "API is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)