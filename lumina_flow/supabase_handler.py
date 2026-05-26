"""
Lumina Flow - Supabase Handler
Isolated logic for Supabase authentication and database operations
"""

import os
import io
import base64
import uuid
import logging
from datetime import datetime
from werkzeug.utils import secure_filename
from supabase import create_client, Client
from .config import Config
from PIL import Image, ImageOps


logger = logging.getLogger(__name__)


class SupabaseHandler:
    """Handler for Supabase operations"""
    
    def __init__(self):
        """Initialize Supabase client"""
        self.supabase_url = Config.SUPABASE_URL
        self.supabase_key = Config.SUPABASE_KEY
        self.supabase_service_key = Config.SUPABASE_SERVICE_ROLE_KEY
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
        
        self.client: Client = create_client(self.supabase_url, self.supabase_key)
        self.admin_client: Client = create_client(self.supabase_url, self.supabase_service_key)
    
    def create_test_profile(self, user_id: str, email: str, full_name: str = 'Test User', plan: str = 'pro') -> dict:
        """
        Create a test user in Supabase Auth and profile (for testing purposes)

        Args:
            user_id: UUID for the test user
            email: Email address
            full_name: User's full name
            plan: Subscription plan

        Returns:
            Dictionary with success status
        """
        try:
            # First, try to create the user in Supabase Auth using admin API
            try:
                # Create user in auth.users (requires service role)
                auth_response = self.admin_client.auth.admin.create_user({
                    'email': email,
                    'password': 'testpassword123',
                    'email_confirm': True,
                    'user_metadata': {'full_name': full_name}
                })

                if auth_response.user:
                    user_id = auth_response.user.id  # Use the actual UUID from Supabase
            except Exception as auth_error:
                # User might already exist, that's OK
                logger.info("Auth user creation (may already exist): %s", auth_error)

            # Check if profile already exists
            response = self.admin_client.table('profiles') \
                .select('id') \
                .eq('id', user_id) \
                .execute()

            if response.data and len(response.data) > 0:
                return {'success': True, 'user_id': user_id, 'message': 'Profile already exists'}

            # Create profile directly
            from datetime import datetime
            profile_data = {
                'id': user_id,
                'email': email,
                'full_name': full_name,
                'plan': plan,
                'subscription_status': 'active',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }

            self.admin_client.table('profiles').insert(profile_data).execute()
            return {'success': True, 'user_id': user_id, 'message': 'Test profile created'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_professions(self) -> dict:
        """
        Get all active professions

        Returns:
            Dictionary with list of professions
        """
        try:
            response = self.admin_client.table('professions') \
                .select('*') \
                .eq('is_active', True) \
                .order('name') \
                .execute()
            return {
                'success': True,
                'data': response.data if response.data else []
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'data': []
            }
    
    def sign_out(self, access_token: str) -> dict:
        """
        Sign out a user (deprecated - using Flask-Login now)
        
        Args:
            access_token: User access token
            
        Returns:
            Dictionary with success status or error
        """
        try:
            self.client.auth.sign_out()
            return {'success': True}
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_user_subscription(self, user_id: str) -> dict:
        """
        Get user subscription information combining user and profile tables
        
        Args:
            user_id: User ID
            
        Returns:
            Dictionary with subscription data or error
        """
        try:
            user_plan = 'free'

            user_response = self.admin_client.table('users') \
                .select('plan') \
                .eq('id', user_id) \
                .execute()

            if user_response.data:
                user_plan = user_response.data[0].get('plan', 'free')

            profile_response = self.admin_client.table('profiles') \
                .select('plan, subscription_status, stripe_customer_id, stripe_subscription_id, next_billing_date') \
                .eq('user_id', user_id) \
                .execute()

            if profile_response.data:
                profile = profile_response.data[0]
                return {
                    'success': True,
                    'plan': profile.get('plan', user_plan) or user_plan,
                    'subscription_status': profile.get('subscription_status', 'inactive'),
                    'stripe_customer_id': profile.get('stripe_customer_id'),
                    'stripe_subscription_id': profile.get('stripe_subscription_id'),
                    'next_billing_date': profile.get('next_billing_date')
                }

            return {
                'success': True,
                'plan': user_plan,
                'subscription_status': 'inactive',
                'stripe_customer_id': None,
                'stripe_subscription_id': None,
                'next_billing_date': None
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def update_user_subscription(self, user_id: str, plan: str, subscription_status: str, 
                                   stripe_customer_id: str = None, stripe_subscription_id: str = None,
                                   next_billing_date: str = None) -> dict:
        """
        Update user subscription information
        
        Args:
            user_id: User ID
            plan: Plan type (free, basic, pro, enterprise)
            subscription_status: Subscription status (active, inactive, trial)
            stripe_customer_id: Stripe customer ID
            stripe_subscription_id: Stripe subscription ID
            next_billing_date: Next billing date
            
        Returns:
            Dictionary with success status or error
        """
        try:
            update_data = {
                'plan': plan,
                'subscription_status': subscription_status
            }
            
            if stripe_customer_id is not None:
                update_data['stripe_customer_id'] = stripe_customer_id
            if stripe_subscription_id is not None:
                update_data['stripe_subscription_id'] = stripe_subscription_id
            if next_billing_date is not None:
                update_data['next_billing_date'] = next_billing_date
            
            response = self.admin_client.table('profiles') \
                .upsert({**update_data, 'user_id': user_id}, on_conflict='user_id') \
                .execute()

            # Keep users table in sync
            self.admin_client.table('users') \
                .update({'plan': plan, 'updated_at': datetime.now().isoformat()}) \
                .eq('id', user_id) \
                .execute()

            return {
                'success': True,
                'data': response.data
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def update_user_profile(self, user_id: str, full_name: str = None, profession_id: str = None, logo_url: str = None, company_name: str = None, whatsapp: str = None, profile_photo_url: str = None) -> dict:
        """
        Update user profile

        Args:
            user_id: User ID
            full_name: User's full name
            profession_id: UUID of profession
            logo_url: URL to logo image
            company_name: Company name
            whatsapp: WhatsApp number
            profile_photo_url: URL to profile photo

        Returns:
            Dictionary with success status
        """
        try:
            update_data = {}
            if full_name:
                update_data['full_name'] = full_name
            if profession_id:
                update_data['profession_id'] = profession_id
            if logo_url:
                update_data['logo_url'] = logo_url
            if company_name:
                update_data['company_name'] = company_name
            if whatsapp:
                update_data['whatsapp'] = whatsapp
            if profile_photo_url:
                update_data['profile_photo_url'] = profile_photo_url

            if not update_data:
                return {'success': True, 'message': 'No data to update'}

            # Check if profile exists
            check_response = self.admin_client.table('profiles') \
                .select('id') \
                .eq('user_id', user_id) \
                .execute()

            if not check_response.data or len(check_response.data) == 0:
                # Profile doesn't exist, create it
                from datetime import datetime
                profile_data = {
                    'user_id': user_id,
                    'email': '',  # Will be updated if needed
                    'full_name': full_name or '',
                    'plan': 'free',
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                }
                if whatsapp:
                    profile_data['whatsapp'] = whatsapp
                if profile_photo_url:
                    profile_data['profile_photo_url'] = profile_photo_url
                
                self.admin_client.table('profiles').insert(profile_data).execute()
                return {'success': True, 'message': 'Profile created'}
            else:
                # Profile exists, update it
                self.admin_client.table('profiles') \
                    .update(update_data) \
                    .eq('user_id', user_id) \
                    .execute()

            return {'success': True}
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def get_user_profile(self, user_id: str) -> dict:
        """
        Get user profile data

        Args:
            user_id: User ID

        Returns:
            Dictionary with profile data or error
        """
        try:
            response = self.admin_client.table('profiles') \
                .select('*') \
                .eq('user_id', user_id) \
                .execute()

            if response.data and len(response.data) > 0:
                return {
                    'success': True,
                    'data': response.data[0]
                }
            else:
                return {
                    'success': False,
                    'error': 'Profile not found'
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def get_quotation_templates_by_profession(self, profession_id: str) -> dict:
        """
        Get quotation templates for a specific profession

        Args:
            profession_id: Profession UUID

        Returns:
            Dictionary with list of templates
        """
        try:
            response = self.admin_client.table('quotation_templates') \
                .select('*') \
                .eq('profession_id', profession_id) \
                .eq('is_active', True) \
                .order('sort_order') \
                .execute()
            return {
                'success': True,
                'data': response.data if response.data else []
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'data': []
            }

    def compress_image(self, image_file, max_size_kb=150, max_dimension=800) -> tuple:
        """
        Compress and optimize image for web upload
        
        Args:
            image_file: File object or bytes
            max_size_kb: Maximum file size in KB
            max_dimension: Maximum width/height in pixels
            
        Returns:
            Tuple of (compressed_bytes, format, width, height)
        """
        try:
            # Open image
            if hasattr(image_file, 'read'):
                img = Image.open(image_file)
                image_file.seek(0)  # Reset pointer
            else:
                img = Image.open(io.BytesIO(image_file))
            
            # Convert to RGB if necessary (for PNG with transparency or CMYK)
            if img.mode in ('RGBA', 'P', 'CMYK'):
                img = img.convert('RGB')
            
            # Auto-orient based on EXIF data
            img = ImageOps.exif_transpose(img)
            
            # Resize if larger than max_dimension
            width, height = img.size
            if width > max_dimension or height > max_dimension:
                ratio = min(max_dimension / width, max_dimension / height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                width, height = new_width, new_height
            
            # Try different quality levels to meet size requirement
            quality = 95
            min_quality = 60
            format_name = 'JPEG'
            
            while quality >= min_quality:
                buffer = io.BytesIO()
                img.save(buffer, format=format_name, quality=quality, optimize=True, progressive=True)
                size_kb = buffer.tell() / 1024
                
                if size_kb <= max_size_kb:
                    buffer.seek(0)
                    return (buffer.read(), format_name.lower(), width, height)
                
                quality -= 5
            
            # If still too large, reduce dimensions more aggressively
            if quality < min_quality:
                ratio = 0.7
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                buffer = io.BytesIO()
                img.save(buffer, format=format_name, quality=min_quality, optimize=True, progressive=True)
                buffer.seek(0)
                return (buffer.read(), format_name.lower(), new_width, new_height)
            
            buffer.seek(0)
            return (buffer.read(), format_name.lower(), width, height)
            
        except Exception as e:
            return (None, None, 0, 0)

    def upload_file_to_storage(self, file_content: bytes, filename: str, bucket_name: str = 'avatars') -> str:
        """
        Uploads a file to Supabase Storage and returns the public URL.
        Args:
            file_content: The file content in bytes.
            filename: The desired filename (e.g., 'user_avatar.jpg').
            bucket_name: The name of the Supabase Storage bucket.
        Returns:
            The public URL of the uploaded file, or None if upload fails.
        """
        try:
            # Supabase client for storage operations. Using the public key.
            # For more security, consider using service key or presigned URLs.
            storage_client = create_client(self.supabase_url, self.supabase_key)

            logger.info(
                "[Supabase Storage] Upload attempt",
                extra={
                    'filename': filename,
                    'bucket': bucket_name,
                    'size_bytes': len(file_content)
                }
            )
            
            # Upload the file
            upload_response = storage_client.storage.from_(bucket_name).upload(filename, file_content, {
                'content-type': 'image/jpeg', # Assuming JPEG, adjust if content-type is known more precisely
                'upsert': 'true'  # Allow overwriting existing files
            })

            # Check for errors - storage3 uses different API
            if hasattr(upload_response, 'error') and upload_response.error:
                logger.error(
                    "[Supabase Storage] Upload error",
                    extra={'filename': filename, 'bucket': bucket_name, 'error': upload_response.error}
                )
                return None

            logger.info(
                "[Supabase Storage] Upload successful",
                extra={'filename': filename, 'bucket': bucket_name}
            )

            # Construct the public URL (requires the bucket to be public)
            public_url = f"{self.supabase_url}/storage/v1/object/public/{bucket_name}/{filename}"
            logger.debug(
                "[Supabase Storage] Generated public URL",
                extra={'filename': filename, 'bucket': bucket_name, 'public_url': public_url}
            )

            return public_url
        except Exception as e:
            logger.exception("[Supabase Storage] Exception during upload", extra={'filename': filename})
            return None

    def upload_profile_image(self, user_id: str, image_file, filename: str) -> dict:
        """
        Upload compressed profile image to Supabase Storage
        
        Args:
            user_id: User ID
            image_file: File object
            filename: Original filename
            
        Returns:
            Dictionary with success status and public URL
        """
        try:
            # Compress image
            compressed_bytes, format_name, width, height = self.compress_image(image_file)
            
            if not compressed_bytes:
                return {'success': False, 'error': 'Failed to compress image'}
            # Generate safe filename
            safe_filename = f"{user_id}.{format_name}"
            file_path = f"{user_id}/{safe_filename}"
            
            # Upload to Supabase Storage
            bucket_name = 'profile-images'
            
            # Check if bucket exists, if not create it (requires admin)
            try:
                self.admin_client.storage.get_bucket(bucket_name)
            except Exception:
                # Bucket doesn't exist, create it
                try:
                    self.admin_client.storage.create_bucket(
                        bucket_name,
                        options={'public': True, 'file_size_limit': 157286}  # 150KB in bytes
                    )
                except Exception as bucket_error:
                    logger.info("Bucket creation (may already exist): %s", bucket_error)
            
            # Upload file
            result = self.admin_client.storage \
                .from_(bucket_name) \
                .upload(file_path, compressed_bytes, {
                    'content-type': f'image/{format_name}',
                    'upsert': True  # Overwrite if exists
                })
            
            # Get public URL
            public_url = self.admin_client.storage \
                .from_(bucket_name) \
                .get_public_url(file_path)
            # Update profile with new logo URL
            self.update_user_profile(user_id, logo_url=public_url)
            return {
                'success': True,
                'url': public_url,
                'path': file_path,
                'size_kb': len(compressed_bytes) / 1024,
                'width': width,
                'height': height
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def delete_profile_image(self, user_id: str) -> dict:
        """
        Delete user's profile image from storage
        Args:
            user_id: User ID
        Returns:
            Dictionary with success status
        """
        try:
            bucket_name = 'profile-images'
            
            # List all files in user's folder
            try:
                files = self.admin_client.storage \
                    .from_(bucket_name) \
                    .list(f"{user_id}/")
                
                # Delete each file
                for file in files:
                    file_path = f"{user_id}/{file['name']}"
                    self.admin_client.storage \
                        .from_(bucket_name) \
                        .remove([file_path])
                
                return {'success': True, 'message': 'Profile image deleted'}
            except Exception as list_error:
                # Folder might not exist
                return {'success': True, 'message': 'No profile image to delete'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def delete_user_account(self, user_id: str) -> dict:
        """
        Delete user account and all associated data including profile image
        Args:
            user_id: User ID
        Returns:
            Dictionary with success status
        """
        try:
            # 1. Delete profile image first
            self.delete_profile_image(user_id)
            
            # 2. Delete all user's quotations
            self.admin_client.table('quotations') \
                .delete() \
                .eq('user_id', user_id) \
                .execute()
            
            # 3. Delete user profile
            self.admin_client.table('profiles') \
                .delete() \
                .eq('user_id', user_id) \
                .execute()
            
            # 4. Delete user from auth (requires admin privileges)
            self.admin_client.auth.admin.delete_user(user_id)
            
            return {'success': True, 'message': 'User account deleted successfully'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def delete_quotation(self, user_id: str, quotation_id: str) -> dict:
        """
        Delete a quotation
        Args:
            user_id: User ID
            quotation_id: Quotation ID
        Returns:
            Result dict with success status
        """
        try:
            response = self.admin_client.table('quotations') \
                .delete() \
                .eq('user_id', user_id) \
                .eq('id', quotation_id) \
                .execute()
            
            return {'success': True, 'data': response.data}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def update_quotation_status(self, user_id: str, quotation_id: str, status: str) -> dict:
        """
        Update the status of a quotation
        Args:
            user_id: User ID
            quotation_id: Quotation ID
            status: New status (pending, accepted, rejected)
        Returns:
            Result dict with success status
        """
        try:
            response = self.admin_client.table('quotations') \
                .update({'status': status}) \
                .eq('user_id', user_id) \
                .eq('id', quotation_id) \
                .execute()
            
            return {'success': True, 'data': response.data}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def update_quotation_expiry(self, user_id: str, quotation_id: str, expiry_date: str) -> dict:
        """
        Update the expiry date of a quotation
        Args:
            user_id: User ID
            quotation_id: Quotation ID
            expiry_date: New expiry date (YYYY-MM-DD format)
        Returns:
            Result dict with success status
        """
        try:
            response = self.admin_client.table('quotations') \
                .update({'expiry_date': expiry_date}) \
                .eq('user_id', user_id) \
                .eq('id', quotation_id) \
                .execute()
            
            return {'success': True, 'data': response.data}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def update_quotation(self, user_id: str, quotation_id: str, update_data: dict = None, **fields) -> dict:
        """
        Update quotation fields
        Args:
            user_id: User ID
            quotation_id: Quotation ID
            update_data: Dictionary of fields to update
            **fields: Optional keyword arguments for backwards compatibility
        Returns:
            Result dict with success status
        """
        payload = {}
        if isinstance(update_data, dict):
            payload.update(update_data)
        if fields:
            payload.update(fields)

        if not payload:
            return {'success': False, 'error': 'No fields provided for update'}

        try:
            response = self.admin_client.table('quotations') \
                .update(payload) \
                .eq('user_id', user_id) \
                .eq('id', quotation_id) \
                .execute()
            
            return {'success': True, 'data': response.data}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def update_user_quotation_currency(self, user_id: str, currency: str) -> dict:
        """
        Update currency of all quotations for a user
        Args:
            user_id: User ID
            currency: Currency code (BRL or GBP)
        Returns:
            Result dict with success status
        """
        try:
            response = self.client.table('quotations') \
                .update({'currency': currency}) \
                .eq('user_id', user_id) \
                .execute()
            
            return {'success': True, 'data': response.data}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def create_quotation(self, user_id: str, client_name: str, service_description: str,
                         value: float, currency: str = 'BRL', expiry_date: str = None,
                         quotation_type: str = 'quick', phone: str = None, address: str = None,
                         items: list = None, discount: float = 0, notes: str = None,
                         template: str = 'quick_modern.html') -> dict:
        """
        Create a new quotation
        Args:
            user_id: User ID
            client_name: Client name
            service_description: Service description
            value: Quotation value
            currency: Currency code
            expiry_date: Expiry date (YYYY-MM-DD)
            quotation_type: 'quick' or 'detailed'
            phone: Client phone number
            address: Client address
            items: List of items for detailed quotations
            discount: Discount amount
            notes: Additional notes
            template: Template file name
            
        Returns:
            Dictionary with created quotation or error
        """
        try:
            data = {
                'user_id': user_id,
                'client_name': client_name,
                'service_description': service_description,
                'value': value,
                'currency': currency,
                'status': 'pending',
                'quotation_type': quotation_type,
                'template': template
            }
            if expiry_date:
                data['expiry_date'] = expiry_date
            if phone:
                data['phone'] = phone
            if address:
                data['address'] = address
            if items:
                data['items'] = items
            if discount:
                data['discount'] = discount
            if notes:
                data['notes'] = notes
            
            response = self.admin_client.table('quotations').insert(data).execute()
            return {
                'success': True,
                'data': response.data[0] if response.data else None
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_user_quotations(self, user_id: str, access_token: str = None) -> dict:
        """
        Get all quotations for a user

        Args:
            user_id: User ID
            access_token: Optional access token for authenticated request (respects RLS)
        Returns:
            Dictionary with list of quotations or error
        """
        try:
            # Use authenticated client if access_token provided (respects RLS)
            # Otherwise use admin_client (bypasses RLS - only for admin operations)
            client = self.client if access_token else self.admin_client

            response = client.table('quotations') \
                .select('*') \
                .eq('user_id', user_id) \
                .order('created_at', desc=True) \
                .execute()
            return {
                'success': True,
                'data': response.data
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def count_user_quotations(self, user_id: str) -> dict:
        """
        Count user quotations
        
        Args:
            user_id: User ID
            
        Returns:
            Dictionary with count or error
        """
        try:
            response = self.admin_client.table('quotations') \
                .select('id', count='exact') \
                .eq('user_id', user_id) \
                .execute()
            return {
                'success': True,
                'count': len(response.data) if response.data else 0
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def get_quotation_by_id(self, user_id: str, quotation_id: str) -> dict:
        """
        Get a specific quotation by ID

        Args:
            user_id: User ID
            quotation_id: Quotation ID

        Returns:
            Dictionary with quotation data or error
        """
        try:
            response = self.admin_client.table('quotations') \
                .select('*') \
                .eq('id', quotation_id) \
                .eq('user_id', user_id) \
                .execute()

            if response.data and len(response.data) > 0:
                return {
                    'success': True,
                    'data': response.data[0]
                }
            else:
                return {
                    'success': False,
                    'error': 'Quotation not found'
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def get_public_quotation(self, quotation_id: str) -> dict:
        """
        Get a quotation by ID without requiring an authenticated owner.

        Args:
            quotation_id: Quotation ID

        Returns:
            Dictionary with quotation data or error
        """
        try:
            response = self.admin_client.table('quotations') \
                .select('*') \
                .eq('id', quotation_id) \
                .execute()

            if response.data and len(response.data) > 0:
                return {
                    'success': True,
                    'data': response.data[0]
                }
            else:
                return {
                    'success': False,
                    'error': 'Quotation not found'
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def is_pro_user(self, user_id: str) -> bool:
        """
        Check if user is a Pro subscriber
        
        Args:
            user_id: User ID
            
        Returns:
            Boolean indicating if user is Pro
        """
        subscription = self.get_user_subscription(user_id)
        if subscription.get('success'):
            return subscription.get('plan') in ('basic', 'pro', 'enterprise') and subscription.get('subscription_status') == 'active'
        return False


# Singleton instance
_supabase_handler = None


def get_supabase_handler():
    """Get or create Supabase handler instance"""
    global _supabase_handler
    if _supabase_handler is None:
        _supabase_handler = SupabaseHandler()
    return _supabase_handler

