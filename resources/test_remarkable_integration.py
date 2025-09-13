#!/usr/bin/env python3
"""
Comprehensive integration test for ReMarkable workflow.

This script tests the complete workflow from markdown file processing
to ReMarkable device upload, including all the key functions:
- markdown to PDF conversion
- add_pdf_with_metadata() integration
- hash_from_title() document lookup
- add_with_metadata_if_new() duplicate checking
- xochitl restart functionality

Run this script to validate the complete ReMarkable integration.
"""

import os
import sys
from pathlib import Path
import time
import logging
from typing import Dict, Any

# Add the readmarkable directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from services.remarkable_service import get_remarkable_service, init_remarkable_service
from services.markdown_service import get_markdown_service, init_markdown_service
from services.network_service import init_network_service
from config.settings import get_config, init_config
from utils.logger import get_logger, setup_logging


class ReMarkableIntegrationTest:
    """Comprehensive test suite for ReMarkable integration."""
    
    def __init__(self):
        """Initialize the test suite."""
        self.logger = get_logger()
        self.config = get_config()
        
        # Initialize services
        self.remarkable_service = None
        self.markdown_service = None
        
        # Test results tracking
        self.test_results = {
            'passed': 0,
            'failed': 0,
            'errors': []
        }
    
    def setup(self) -> bool:
        """Setup test environment and services."""
        try:
            self.logger.info("Setting up ReMarkable integration test...")
            
            # Configure ReMarkable connection using SSH script credentials
            # Try USB first, then WiFi
            hostname = "10.11.99.1"  # USB connection
            password = "dyovaamsE"
            
            # Check if USB is accessible, otherwise use WiFi
            import subprocess
            try:
                result = subprocess.run(
                    ["ping", "-c", "1", "-W", "1", hostname],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if result.returncode != 0:
                    # Try WiFi IP
                    hostname = "10.97.253.97"
                    self.logger.info(f"USB not accessible, trying WiFi at {hostname}")
                else:
                    self.logger.info(f"Using USB connection at {hostname}")
            except Exception:
                self.logger.info(f"Using default USB connection at {hostname}")
            
            # Initialize network service
            from services.network_service import get_network_service
            network_service = init_network_service()
            
            # Set connection details
            network_service.set_connection_details(hostname=hostname, password=password)
            self.logger.info(f"Network service configured for {hostname}")
            
            # Initialize other services
            self.remarkable_service = init_remarkable_service()
            self.markdown_service = init_markdown_service()
            
            # Test connection
            if network_service.connect():
                self.logger.info("Successfully connected to ReMarkable device")
            else:
                self.logger.warning("Could not establish connection to ReMarkable device")
            
            self.logger.info("Services initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Setup failed: {e}")
            return False
    
    def test_markdown_to_pdf_conversion(self, farm_diary_path: Path) -> bool:
        """Test markdown to PDF conversion."""
        self.logger.info("Testing markdown to PDF conversion...")
        
        try:
            if not farm_diary_path.exists():
                raise FileNotFoundError(f"Farm diary file not found: {farm_diary_path}")
            
            # Create output directory
            output_dir = Path("test_output")
            output_dir.mkdir(exist_ok=True)
            
            # Convert markdown to PDF
            pdf_path = self.markdown_service.process_markdown_file(
                farm_diary_path, 
                output_dir, 
                upload_to_remarkable=False
            )
            
            if pdf_path and pdf_path.exists():
                self.logger.info(f"✓ PDF conversion successful: {pdf_path}")
                self.test_results['passed'] += 1
                return True
            else:
                self.logger.error("✗ PDF conversion failed")
                self.test_results['failed'] += 1
                self.test_results['errors'].append("PDF conversion failed")
                return False
                
        except Exception as e:
            self.logger.error(f"✗ PDF conversion test failed: {e}")
            self.test_results['failed'] += 1
            self.test_results['errors'].append(f"PDF conversion error: {e}")
            return False
    
    def test_add_pdf_with_metadata(self, pdf_path: Path, title: str) -> str:
        """Test adding PDF with metadata to ReMarkable."""
        self.logger.info(f"Testing add_pdf_with_metadata for: {title}")
        
        try:
            if not pdf_path.exists():
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")
            
            # Add PDF to ReMarkable with metadata
            document_uuid = self.remarkable_service.add_pdf_with_metadata(pdf_path, title)
            
            if document_uuid:
                self.logger.info(f"✓ PDF added successfully: {title} (UUID: {document_uuid})")
                self.test_results['passed'] += 1
                return document_uuid
            else:
                self.logger.error(f"✗ Failed to add PDF: {title}")
                self.test_results['failed'] += 1
                self.test_results['errors'].append(f"Failed to add PDF: {title}")
                return None
                
        except Exception as e:
            self.logger.error(f"✗ add_pdf_with_metadata test failed: {e}")
            self.test_results['failed'] += 1
            self.test_results['errors'].append(f"add_pdf_with_metadata error: {e}")
            return None
    
    def test_hash_from_title(self, title: str, expected_uuid: str = None) -> bool:
        """Test document lookup using hash_from_title."""
        self.logger.info(f"Testing hash_from_title for: {title}")
        
        try:
            found_uuid = self.remarkable_service.hash_from_title(title)
            
            if found_uuid:
                self.logger.info(f"✓ Document found: {title} (UUID: {found_uuid})")
                
                if expected_uuid and found_uuid == expected_uuid:
                    self.logger.info("✓ UUID matches expected value")
                elif expected_uuid:
                    self.logger.warning(f"UUID mismatch: expected {expected_uuid}, got {found_uuid}")
                
                self.test_results['passed'] += 1
                return True
            else:
                self.logger.warning(f"✗ Document not found: {title}")
                self.test_results['failed'] += 1
                self.test_results['errors'].append(f"Document not found: {title}")
                return False
                
        except Exception as e:
            self.logger.error(f"✗ hash_from_title test failed: {e}")
            self.test_results['failed'] += 1
            self.test_results['errors'].append(f"hash_from_title error: {e}")
            return False
    
    def test_add_with_metadata_if_new(self, pdf_path: Path, title: str) -> str:
        """Test duplicate checking with add_with_metadata_if_new."""
        self.logger.info(f"Testing add_with_metadata_if_new for: {title}")
        
        try:
            if not pdf_path.exists():
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")
            
            # First call - should add if new, or return existing UUID
            document_uuid = self.remarkable_service.add_with_metadata_if_new(pdf_path, title)
            
            if document_uuid:
                self.logger.info(f"✓ Document handled: {title} (UUID: {document_uuid})")
                
                # Second call - should return same UUID (duplicate detection)
                duplicate_uuid = self.remarkable_service.add_with_metadata_if_new(pdf_path, title)
                
                if duplicate_uuid == document_uuid:
                    self.logger.info("✓ Duplicate detection working correctly")
                    self.test_results['passed'] += 1
                    return document_uuid
                else:
                    self.logger.error(f"✗ Duplicate detection failed: {document_uuid} != {duplicate_uuid}")
                    self.test_results['failed'] += 1
                    self.test_results['errors'].append("Duplicate detection failed")
                    return document_uuid
            else:
                self.logger.error(f"✗ Failed to add document: {title}")
                self.test_results['failed'] += 1
                self.test_results['errors'].append(f"Failed to add document: {title}")
                return None
                
        except Exception as e:
            self.logger.error(f"✗ add_with_metadata_if_new test failed: {e}")
            self.test_results['failed'] += 1
            self.test_results['errors'].append(f"add_with_metadata_if_new error: {e}")
            return None
    
    def test_last_read_document(self) -> bool:
        """Test getting the last read document."""
        self.logger.info("Testing last_read_document...")
        
        try:
            last_uuid = self.remarkable_service.last_read_document()
            
            if last_uuid:
                self.logger.info(f"✓ Last read document: {last_uuid}")
                
                # Try to get document info
                doc_info = self.remarkable_service.get_document_info(last_uuid)
                if doc_info:
                    self.logger.info(f"✓ Document info: {doc_info.get('title', 'Unknown')}")
                
                self.test_results['passed'] += 1
                return True
            else:
                self.logger.warning("✗ No last read document found")
                self.test_results['failed'] += 1
                self.test_results['errors'].append("No last read document found")
                return False
                
        except Exception as e:
            self.logger.error(f"✗ last_read_document test failed: {e}")
            self.test_results['failed'] += 1
            self.test_results['errors'].append(f"last_read_document error: {e}")
            return False
    
    def test_complete_workflow(self, farm_diary_path: Path) -> bool:
        """Test the complete workflow from markdown to ReMarkable upload."""
        self.logger.info("Testing complete workflow...")
        
        try:
            if not farm_diary_path.exists():
                raise FileNotFoundError(f"Farm diary file not found: {farm_diary_path}")
            
            # Create output directory
            workflow_output_dir = Path("workflow_test_output")
            workflow_output_dir.mkdir(exist_ok=True)
            
            title = f"Farm_Operations_Log_{int(time.time())}"
            
            # Use the new integrated workflow method
            document_uuid = self.markdown_service.process_and_upload_markdown(
                farm_diary_path,
                workflow_output_dir,
                title_override=title
            )
            
            if document_uuid:
                self.logger.info(f"✓ Complete workflow successful: {title} (UUID: {document_uuid})")
                
                # Verify the document exists on device
                found_uuid = self.remarkable_service.hash_from_title(title)
                if found_uuid == document_uuid:
                    self.logger.info("✓ Document verified on device")
                    self.test_results['passed'] += 1
                    return True
                else:
                    self.logger.error("✗ Document verification failed")
                    self.test_results['failed'] += 1
                    self.test_results['errors'].append("Document verification failed")
                    return False
            else:
                self.logger.error("✗ Complete workflow failed")
                self.test_results['failed'] += 1
                self.test_results['errors'].append("Complete workflow failed")
                return False
                
        except Exception as e:
            self.logger.error(f"✗ Complete workflow test failed: {e}")
            self.test_results['failed'] += 1
            self.test_results['errors'].append(f"Complete workflow error: {e}")
            return False
    
    def test_xochitl_restart(self) -> bool:
        """Test xochitl service restart functionality."""
        self.logger.info("Testing xochitl restart...")
        
        try:
            # This tests the internal restart method
            success = self.remarkable_service._restart_xochitl()
            
            if success:
                self.logger.info("✓ xochitl restart successful")
                self.test_results['passed'] += 1
                return True
            else:
                self.logger.error("✗ xochitl restart failed")
                self.test_results['failed'] += 1
                self.test_results['errors'].append("xochitl restart failed")
                return False
                
        except Exception as e:
            self.logger.error(f"✗ xochitl restart test failed: {e}")
            self.test_results['failed'] += 1
            self.test_results['errors'].append(f"xochitl restart error: {e}")
            return False
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all integration tests."""
        self.logger.info("=" * 60)
        self.logger.info("STARTING REMARKABLE INTEGRATION TESTS")
        self.logger.info("=" * 60)
        
        # Setup
        if not self.setup():
            return {'error': 'Setup failed', 'results': self.test_results}
        
        # Find farm diary file
        farm_diary_path = Path("../farmdiary_001.md")
        if not farm_diary_path.exists():
            farm_diary_path = Path("farmdiary_001.md")
        
        if not farm_diary_path.exists():
            self.logger.error("Farm diary file not found. Please ensure farmdiary_001.md exists.")
            return {'error': 'Farm diary file not found', 'results': self.test_results}
        
        # Test 1: Markdown to PDF conversion
        self.logger.info("\n1. Testing Markdown to PDF Conversion")
        self.logger.info("-" * 40)
        pdf_success = self.test_markdown_to_pdf_conversion(farm_diary_path)
        
        if pdf_success:
            pdf_path = Path("test_output/farmdiary_001.pdf")
            
            # Test 2: Add PDF with metadata
            self.logger.info("\n2. Testing add_pdf_with_metadata")
            self.logger.info("-" * 40)
            test_title = f"Farm_Diary_Entry_{int(time.time())}"
            document_uuid = self.test_add_pdf_with_metadata(pdf_path, test_title)
            
            # Test 3: Document lookup
            self.logger.info("\n3. Testing hash_from_title")
            self.logger.info("-" * 40)
            self.test_hash_from_title(test_title, document_uuid)
            
            # Test 4: Duplicate checking
            self.logger.info("\n4. Testing add_with_metadata_if_new")
            self.logger.info("-" * 40)
            duplicate_title = f"Farm_Report_{int(time.time())}"
            self.test_add_with_metadata_if_new(pdf_path, duplicate_title)
        
        # Test 5: Last read document
        self.logger.info("\n5. Testing last_read_document")
        self.logger.info("-" * 40)
        self.test_last_read_document()
        
        # Test 6: Complete workflow
        self.logger.info("\n6. Testing Complete Workflow")
        self.logger.info("-" * 40)
        self.test_complete_workflow(farm_diary_path)
        
        # Test 7: xochitl restart
        self.logger.info("\n7. Testing xochitl Restart")
        self.logger.info("-" * 40)
        self.test_xochitl_restart()
        
        # Results summary
        self.logger.info("\n" + "=" * 60)
        self.logger.info("TEST RESULTS SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info(f"Tests Passed: {self.test_results['passed']}")
        self.logger.info(f"Tests Failed: {self.test_results['failed']}")
        
        if self.test_results['errors']:
            self.logger.info("\nErrors encountered:")
            for error in self.test_results['errors']:
                self.logger.error(f"  - {error}")
        
        if self.test_results['failed'] == 0:
            self.logger.info("\n✓ ALL TESTS PASSED - ReMarkable integration is working correctly.")
        else:
            self.logger.warning(f"\n⚠ {self.test_results['failed']} test(s) failed. Please review the errors above.")
        
        return {
            'success': self.test_results['failed'] == 0,
            'results': self.test_results
        }


def main():
    """Run the integration test suite."""
    # Initialize config and logging systems first
    init_config()
    setup_logging()
    
    # Set up additional logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Run tests
    test_suite = ReMarkableIntegrationTest()
    results = test_suite.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if results.get('success', False) else 1)


if __name__ == "__main__":
    main()