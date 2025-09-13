"""
ReMarkable device integration service for readMarkable.

This module implements the core ReMarkable device operations by replicating
the proven bash function workflow. It handles PDF/EPUB file uploads with proper
metadata creation, document lookup, and state management.
"""

import os
import json
import uuid
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

from services.network_service import get_network_service, CommandResult
from utils.logger import get_logger


class ReMarkableService:
    """
    Service for ReMarkable device integration operations.
    
    Implements the exact logic from proven bash functions for reliable
    document management on reMarkable devices.
    """
    
    def __init__(self):
        """Initialize ReMarkable service."""
        self._logger = get_logger()
        self._network_service = None
        
        # ReMarkable device paths
        self.xochitl_data_path = "/home/root/.local/share/remarkable/xochitl"
        self.xochitl_share_path = "/home/root/.local/share/remarkable/xochitl/"
        
        # Supported file types
        self.supported_extensions = {".pdf", ".epub"}
    
    def _get_network_service(self):
        """Get network service instance with lazy loading."""
        if self._network_service is None:
            try:
                self._network_service = get_network_service()
            except RuntimeError as e:
                self._logger.error(f"Network service not initialized: {e}")
                return None
        return self._network_service
    
    def _execute_command(self, command: str, timeout: Optional[int] = None) -> CommandResult:
        """Execute command on ReMarkable device."""
        network_service = self._get_network_service()
        if not network_service:
            return CommandResult(command, -1, "", "Network service not available", 0.0)
        
        return network_service.execute_command(command, timeout)
    
    def _upload_file(self, local_path: Path, remote_path: str) -> bool:
        """Upload file to ReMarkable device."""
        network_service = self._get_network_service()
        if not network_service:
            self._logger.error("Network service not available for file upload")
            return False
        
        return network_service.upload_file(local_path, remote_path, create_dirs=True)
    
    def _generate_uuid(self) -> str:
        """Generate UUID for new documents."""
        return str(uuid.uuid4())
    
    def _create_metadata_file(self, document_uuid: str, title: str) -> str:
        """Create metadata file content for a document."""
        metadata = {
            "parent": "",
            "type": "DocumentType",
            "visibleName": title
        }
        return json.dumps(metadata)
    
    def _create_content_file(self, file_type: str) -> str:
        """Create content file for a document."""
        content = {
            "fileType": file_type
        }
        return json.dumps(content)
    
    def add_pdf_with_metadata(self, local_pdf_path: Path, title: Optional[str] = None) -> Optional[str]:
        """
        Add PDF to ReMarkable with metadata (replicates addPdfWithMetadata bash function).
        
        Original bash logic:
        cp $1 ~/xochitl-data && 
        echo "{'parent':'','type':'DocumentType','visibleName':'$1'}" | sed s/\\'/\\\"/g > ~/xochitl-data/`echo $1 | sed "s/.pdf//""`.metadata;
        echo '{ "fileType": "pdf" }' > ~/xochitl-data/`echo $1 | sed "s/.pdf//""`.content;
        
        Args:
            local_pdf_path: Path to local PDF file
            title: Document title (defaults to filename without extension)
            
        Returns:
            Document UUID if successful, None otherwise
        """
        if not local_pdf_path.exists():
            self._logger.error(f"PDF file does not exist: {local_pdf_path}")
            return None
        
        if local_pdf_path.suffix.lower() != ".pdf":
            self._logger.error(f"File is not a PDF: {local_pdf_path}")
            return None
        
        # Generate UUID for the document
        document_uuid = self._generate_uuid()
        
        # Use filename without extension as title if not provided
        if title is None:
            title = local_pdf_path.stem
        
        self._logger.info(f"Adding PDF to ReMarkable: {local_pdf_path} as '{title}'")
        
        try:
            # Step 1: Copy PDF file to ~/xochitl-data with UUID as filename
            remote_pdf_path = f"{self.xochitl_data_path}/{document_uuid}.pdf"
            if not self._upload_file(local_pdf_path, remote_pdf_path):
                self._logger.error("Failed to upload PDF file")
                return None
            
            # Step 2: Create metadata file
            metadata_content = self._create_metadata_file(document_uuid, title)
            metadata_command = f"echo '{metadata_content}' > {self.xochitl_data_path}/{document_uuid}.metadata"
            result = self._execute_command(metadata_command)
            if not result.success:
                self._logger.error(f"Failed to create metadata file: {result.stderr}")
                return None
            
            # Step 3: Create content file
            content_json = self._create_content_file("pdf")
            content_command = f"echo '{content_json}' > {self.xochitl_data_path}/{document_uuid}.content"
            result = self._execute_command(content_command)
            if not result.success:
                self._logger.error(f"Failed to create content file: {result.stderr}")
                return None
            
            # Step 4: Restart xochitl service
            if not self._restart_xochitl():
                self._logger.warning("Failed to restart xochitl service")
            
            self._logger.info(f"Successfully added PDF: {title} (UUID: {document_uuid})")
            return document_uuid
            
        except Exception as e:
            self._logger.error(f"Error adding PDF with metadata: {e}")
            return None
    
    def add_epub_with_metadata(self, local_epub_path: Path, title: Optional[str] = None) -> Optional[str]:
        """
        Add EPUB to ReMarkable with metadata (replicates addEpubWithMetadata bash function).
        
        Similar logic to addPdfWithMetadata but for EPUB files.
        
        Args:
            local_epub_path: Path to local EPUB file
            title: Document title (defaults to filename without extension)
            
        Returns:
            Document UUID if successful, None otherwise
        """
        if not local_epub_path.exists():
            self._logger.error(f"EPUB file does not exist: {local_epub_path}")
            return None
        
        if local_epub_path.suffix.lower() != ".epub":
            self._logger.error(f"File is not an EPUB: {local_epub_path}")
            return None
        
        # Generate UUID for the document
        document_uuid = self._generate_uuid()
        
        # Use filename without extension as title if not provided
        if title is None:
            title = local_epub_path.stem
        
        self._logger.info(f"Adding EPUB to ReMarkable: {local_epub_path} as '{title}'")
        
        try:
            # Step 1: Copy EPUB file to ~/xochitl-data with UUID as filename
            remote_epub_path = f"{self.xochitl_data_path}/{document_uuid}.epub"
            if not self._upload_file(local_epub_path, remote_epub_path):
                self._logger.error("Failed to upload EPUB file")
                return None
            
            # Step 2: Create metadata file
            metadata_content = self._create_metadata_file(document_uuid, title)
            metadata_command = f"echo '{metadata_content}' > {self.xochitl_data_path}/{document_uuid}.metadata"
            result = self._execute_command(metadata_command)
            if not result.success:
                self._logger.error(f"Failed to create metadata file: {result.stderr}")
                return None
            
            # Step 3: Create content file
            content_json = self._create_content_file("epub")
            content_command = f"echo '{content_json}' > {self.xochitl_data_path}/{document_uuid}.content"
            result = self._execute_command(content_command)
            if not result.success:
                self._logger.error(f"Failed to create content file: {result.stderr}")
                return None
            
            # Step 4: Restart xochitl service
            if not self._restart_xochitl():
                self._logger.warning("Failed to restart xochitl service")
            
            self._logger.info(f"Successfully added EPUB: {title} (UUID: {document_uuid})")
            return document_uuid
            
        except Exception as e:
            self._logger.error(f"Error adding EPUB with metadata: {e}")
            return None
    
    def hash_from_title(self, title: str) -> Optional[str]:
        """
        Find document UUID by searching metadata files for title (replicates hashFromTitle bash function).
        
        Original bash logic:
        cd ~/.local/share/remarkable/xochitl/ && grep -l -i $1 *metadata | sed 's/.metadata//'
        
        Args:
            title: Title to search for (case-insensitive)
            
        Returns:
            Document UUID if found, None otherwise
        """
        if not title.strip():
            self._logger.error("Title cannot be empty")
            return None
        
        self._logger.debug(f"Searching for document with title: '{title}'")
        
        try:
            # Execute the equivalent bash command
            search_command = f"cd {self.xochitl_share_path} && grep -l -i '{title}' *metadata | sed 's/.metadata//'"
            result = self._execute_command(search_command)
            
            if not result.success:
                if "No such file or directory" in result.stderr:
                    self._logger.debug(f"No metadata files found or no matches for title: '{title}'")
                else:
                    self._logger.warning(f"Search command failed: {result.stderr}")
                return None
            
            # Parse the result - should be UUID(s) separated by newlines
            uuids = result.stdout.strip().split('\n')
            uuids = [uuid.strip() for uuid in uuids if uuid.strip()]
            
            if not uuids:
                self._logger.debug(f"No documents found with title: '{title}'")
                return None
            
            if len(uuids) > 1:
                self._logger.warning(f"Multiple documents found with title '{title}', returning first: {uuids[0]}")
            
            found_uuid = uuids[0]
            self._logger.debug(f"Found document UUID: {found_uuid} for title: '{title}'")
            return found_uuid
            
        except Exception as e:
            self._logger.error(f"Error searching for title '{title}': {e}")
            return None
    
    def add_with_metadata_if_new(self, local_file_path: Path, title: Optional[str] = None) -> Optional[str]:
        """
        Add file with metadata only if it doesn't already exist (replicates addWithMetadataIfNew bash function).
        
        Args:
            local_file_path: Path to local file
            title: Document title (defaults to filename without extension)
            
        Returns:
            Document UUID if added or already exists, None if error
        """
        if title is None:
            title = local_file_path.stem
        
        # Check if document already exists
        existing_uuid = self.hash_from_title(title)
        if existing_uuid:
            self._logger.info(f"Document '{title}' already exists with UUID: {existing_uuid}")
            return existing_uuid
        
        # Add new document based on file type
        file_ext = local_file_path.suffix.lower()
        if file_ext == ".pdf":
            return self.add_pdf_with_metadata(local_file_path, title)
        elif file_ext == ".epub":
            return self.add_epub_with_metadata(local_file_path, title)
        else:
            self._logger.error(f"Unsupported file type: {file_ext}")
            return None
    
    def last_read_document(self) -> Optional[str]:
        """
        Get the most recently opened document (replicates lastReadDocument bash function).
        
        This function would typically look at xochitl state files or logs to determine
        the last accessed document.
        
        Returns:
            UUID of most recently opened document, None if not found
        """
        try:
            # Look for state files that might indicate recent access
            # This is a simplified implementation - the actual bash function may have more logic
            state_command = f"cd {self.xochitl_share_path} && ls -lt *.metadata | head -1 | awk '{{print $9}}' | sed 's/.metadata//'"
            result = self._execute_command(state_command)
            
            if not result.success:
                self._logger.warning(f"Failed to get last read document: {result.stderr}")
                return None
            
            document_uuid = result.stdout.strip()
            if document_uuid:
                self._logger.debug(f"Last read document UUID: {document_uuid}")
                return document_uuid
            
            return None
            
        except Exception as e:
            self._logger.error(f"Error getting last read document: {e}")
            return None
    
    def last_page_from_title(self, title: str) -> Optional[int]:
        """
        Get the last opened page for a specific document (replicates lastPageFromTitle bash function).
        
        Args:
            title: Document title to search for
            
        Returns:
            Last page number if found, None otherwise
        """
        document_uuid = self.hash_from_title(title)
        if not document_uuid:
            self._logger.warning(f"Document not found: '{title}'")
            return None
        
        try:
            # Look for page state information - this may be in .pagedata files or similar
            # This is a simplified implementation
            page_command = f"cd {self.xochitl_share_path} && if [ -f {document_uuid}.pagedata ]; then cat {document_uuid}.pagedata; fi"
            result = self._execute_command(page_command)
            
            if result.success and result.stdout.strip():
                try:
                    # Parse page data - format may vary
                    page_info = json.loads(result.stdout.strip())
                    if "lastOpenedPage" in page_info:
                        page_num = int(page_info["lastOpenedPage"])
                        self._logger.debug(f"Last page for '{title}': {page_num}")
                        return page_num
                except (json.JSONDecodeError, ValueError) as e:
                    self._logger.warning(f"Could not parse page data for '{title}': {e}")
            
            # Default to page 0 if no page data found
            return 0
            
        except Exception as e:
            self._logger.error(f"Error getting last page for '{title}': {e}")
            return None
    
    def _restart_xochitl(self) -> bool:
        """
        Restart the xochitl service on ReMarkable device.
        
        Returns:
            True if restart successful, False otherwise
        """
        try:
            self._logger.debug("Restarting xochitl service")
            result = self._execute_command("systemctl restart xochitl")
            
            if result.success:
                self._logger.info("Successfully restarted xochitl service")
                return True
            else:
                self._logger.error(f"Failed to restart xochitl: {result.stderr}")
                return False
                
        except Exception as e:
            self._logger.error(f"Error restarting xochitl: {e}")
            return False
    
    def get_document_info(self, document_uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a document by UUID.
        
        Args:
            document_uuid: Document UUID
            
        Returns:
            Dictionary with document information, None if not found
        """
        try:
            # Read metadata file
            metadata_command = f"cat {self.xochitl_share_path}{document_uuid}.metadata"
            result = self._execute_command(metadata_command)
            
            if not result.success:
                self._logger.warning(f"Could not read metadata for UUID: {document_uuid}")
                return None
            
            try:
                metadata = json.loads(result.stdout.strip())
            except json.JSONDecodeError:
                self._logger.error(f"Invalid metadata JSON for UUID: {document_uuid}")
                return None
            
            # Read content file
            content_command = f"cat {self.xochitl_share_path}{document_uuid}.content"
            content_result = self._execute_command(content_command)
            
            content_info = {}
            if content_result.success:
                try:
                    content_info = json.loads(content_result.stdout.strip())
                except json.JSONDecodeError:
                    self._logger.warning(f"Invalid content JSON for UUID: {document_uuid}")
            
            # Combine information
            doc_info = {
                "uuid": document_uuid,
                "title": metadata.get("visibleName", "Unknown"),
                "parent": metadata.get("parent", ""),
                "type": metadata.get("type", ""),
                "file_type": content_info.get("fileType", "unknown")
            }
            
            return doc_info
            
        except Exception as e:
            self._logger.error(f"Error getting document info for UUID {document_uuid}: {e}")
            return None
    
    def list_all_documents(self) -> List[Dict[str, Any]]:
        """
        List all documents on the ReMarkable device.
        
        Returns:
            List of document information dictionaries
        """
        try:
            # Get all metadata files
            list_command = f"cd {self.xochitl_share_path} && ls *.metadata | sed 's/.metadata//'"
            result = self._execute_command(list_command)
            
            if not result.success:
                self._logger.warning("No documents found on device")
                return []
            
            uuids = result.stdout.strip().split('\n')
            uuids = [uuid.strip() for uuid in uuids if uuid.strip()]
            
            documents = []
            for document_uuid in uuids:
                doc_info = self.get_document_info(document_uuid)
                if doc_info:
                    documents.append(doc_info)
            
            self._logger.info(f"Found {len(documents)} documents on device")
            return documents
            
        except Exception as e:
            self._logger.error(f"Error listing documents: {e}")
            return []
    
    def delete_document(self, document_uuid: str) -> bool:
        """
        Delete a document from the ReMarkable device.
        
        Args:
            document_uuid: UUID of the document to delete
            
        Returns:
            True if deletion successful, False otherwise
        """
        if not document_uuid.strip():
            self._logger.error("Document UUID cannot be empty")
            return False
        
        try:
            self._logger.info(f"Deleting document with UUID: {document_uuid}")
            
            # Delete all files associated with the document
            delete_command = f"cd {self.xochitl_share_path} && rm -f {document_uuid}.*"
            result = self._execute_command(delete_command)
            
            if not result.success:
                self._logger.error(f"Failed to delete document files: {result.stderr}")
                return False
            
            # Restart xochitl service to refresh
            if not self._restart_xochitl():
                self._logger.warning("Failed to restart xochitl service after deletion")
            
            self._logger.info(f"Successfully deleted document: {document_uuid}")
            return True
            
        except Exception as e:
            self._logger.error(f"Error deleting document {document_uuid}: {e}")
            return False
    
    def rename_document(self, document_uuid: str, new_title: str) -> bool:
        """
        Rename a document on the ReMarkable device.
        
        Args:
            document_uuid: UUID of the document to rename
            new_title: New title for the document
            
        Returns:
            True if rename successful, False otherwise
        """
        if not document_uuid.strip():
            self._logger.error("Document UUID cannot be empty")
            return False
        
        if not new_title.strip():
            self._logger.error("New title cannot be empty")
            return False
        
        try:
            self._logger.info(f"Renaming document {document_uuid} to '{new_title}'")
            
            # Read current metadata
            metadata_command = f"cat {self.xochitl_share_path}{document_uuid}.metadata"
            result = self._execute_command(metadata_command)
            
            if not result.success:
                self._logger.error(f"Could not read metadata for UUID: {document_uuid}")
                return False
            
            try:
                metadata = json.loads(result.stdout.strip())
            except json.JSONDecodeError:
                self._logger.error(f"Invalid metadata JSON for UUID: {document_uuid}")
                return False
            
            # Update title in metadata
            metadata["visibleName"] = new_title.strip()
            
            # Write updated metadata
            updated_metadata = json.dumps(metadata)
            update_command = f"echo '{updated_metadata}' > {self.xochitl_share_path}{document_uuid}.metadata"
            result = self._execute_command(update_command)
            
            if not result.success:
                self._logger.error(f"Failed to update metadata: {result.stderr}")
                return False
            
            # Restart xochitl service to refresh
            if not self._restart_xochitl():
                self._logger.warning("Failed to restart xochitl service after rename")
            
            self._logger.info(f"Successfully renamed document {document_uuid} to '{new_title}'")
            return True
            
        except Exception as e:
            self._logger.error(f"Error renaming document {document_uuid}: {e}")
            return False
    
    def download_document(self, document_uuid: str, local_path: Path) -> bool:
        """
        Download a document from the ReMarkable device.
        
        Args:
            document_uuid: UUID of the document to download
            local_path: Local path where to save the document
            
        Returns:
            True if download successful, False otherwise
        """
        if not document_uuid.strip():
            self._logger.error("Document UUID cannot be empty")
            return False
        
        try:
            self._logger.info(f"Downloading document {document_uuid} to {local_path}")
            
            # Get document info to determine file type
            doc_info = self.get_document_info(document_uuid)
            if not doc_info:
                self._logger.error(f"Could not get document info for UUID: {document_uuid}")
                return False
            
            file_type = doc_info.get("file_type", "pdf")
            
            # Determine remote file path
            remote_file_path = f"{self.xochitl_share_path}{document_uuid}.{file_type}"
            
            # Download the file
            network_service = self._get_network_service()
            if not network_service:
                self._logger.error("Network service not available for file download")
                return False
            
            # Ensure local directory exists
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            if network_service.download_file(remote_file_path, local_path):
                self._logger.info(f"Successfully downloaded document to {local_path}")
                return True
            else:
                self._logger.error(f"Failed to download document from {remote_file_path}")
                return False
            
        except Exception as e:
            self._logger.error(f"Error downloading document {document_uuid}: {e}")
            return False


# Global service instance
_global_remarkable_service: Optional[ReMarkableService] = None


def get_remarkable_service() -> ReMarkableService:
    """
    Get the global ReMarkable service instance.
    
    Returns:
        Global ReMarkableService instance
    """
    global _global_remarkable_service
    if _global_remarkable_service is None:
        _global_remarkable_service = ReMarkableService()
    return _global_remarkable_service


def init_remarkable_service() -> ReMarkableService:
    """
    Initialize the global ReMarkable service.
    
    Returns:
        Initialized ReMarkableService instance
    """
    global _global_remarkable_service
    _global_remarkable_service = ReMarkableService()
    return _global_remarkable_service