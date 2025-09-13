"""
Markdown processing service for readmarkable.

This module handles markdown to PDF conversion, content processing,
and document formatting for reMarkable devices.
"""

import os
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

# Import markdown processing libraries
try:
    import markdown
    from markdown.extensions import tables, codehilite, footnotes
except ImportError:
    markdown = None

# Import PDF generation libraries
try:
    from weasyprint import HTML, CSS
    from weasyprint.text.fonts import FontConfiguration
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.units import inch
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

from utils.logger import get_logger
from config.settings import get_config
from services.remarkable_service import get_remarkable_service


class MarkdownProcessor:
    """Handles markdown content processing and conversion."""
    
    def __init__(self, config: Optional[Any] = None):
        """
        Initialize markdown processor.
        
        Args:
            config: Application configuration
        """
        self._logger = get_logger()
        self.config = config or get_config()
        
        # Setup markdown processor
        self.markdown_processor = None
        if markdown:
            self._setup_markdown_processor()
        else:
            self._logger.warning("Markdown library not available - install with: pip install markdown")
    
    def _setup_markdown_processor(self):
        """Setup the markdown processor with extensions."""
        extensions = ['markdown.extensions.tables']
        
        if self.config.conversion.enable_code_blocks:
            extensions.append('markdown.extensions.codehilite')
        
        if self.config.conversion.enable_footnotes:
            extensions.append('markdown.extensions.footnotes')
        
        self.markdown_processor = markdown.Markdown(
            extensions=extensions,
            extension_configs={
                'codehilite': {
                    'css_class': 'highlight',
                    'use_pygments': True
                }
            }
        )
    
    def process_markdown_content(self, content: str) -> str:
        """
        Process markdown content to HTML.
        
        Args:
            content: Raw markdown content
            
        Returns:
            HTML content
        """
        if not self.markdown_processor:
            self._logger.error("Markdown processor not available")
            return content
        
        try:
            # Process markdown to HTML
            html_content = self.markdown_processor.convert(content)
            
            # Reset processor for next conversion
            self.markdown_processor.reset()
            
            return html_content
            
        except Exception as e:
            self._logger.error(f"Failed to process markdown content: {e}")
            return content
    
    def extract_metadata(self, content: str) -> Dict[str, str]:
        """
        Extract metadata from markdown content.
        
        Args:
            content: Markdown content
            
        Returns:
            Dictionary of extracted metadata
        """
        metadata = {}
        lines = content.split('\n')
        
        # Extract title from first header
        for line in lines:
            if line.startswith('#'):
                metadata['title'] = line.lstrip('#').strip()
                break
        
        # Extract other metadata patterns
        for line in lines[:20]:  # Only check first 20 lines
            if line.startswith('---') and 'yaml_front_matter' not in metadata:
                metadata['yaml_front_matter'] = True
                continue
            
            # Look for author, date patterns
            if line.lower().startswith('author:'):
                metadata['author'] = line.split(':', 1)[1].strip()
            elif line.lower().startswith('date:'):
                metadata['date'] = line.split(':', 1)[1].strip()
            elif line.lower().startswith('tags:'):
                metadata['tags'] = line.split(':', 1)[1].strip()
        
        return metadata


class PDFConverter:
    """Converts HTML/Markdown to PDF using various engines."""
    
    def __init__(self, config: Optional[Any] = None):
        """
        Initialize PDF converter.
        
        Args:
            config: Application configuration
        """
        self._logger = get_logger()
        self.config = config or get_config()
        
        # Determine available PDF engines
        self.engines = []
        if WEASYPRINT_AVAILABLE:
            self.engines.append('weasyprint')
        if REPORTLAB_AVAILABLE:
            self.engines.append('reportlab')
        
        if not self.engines:
            self._logger.warning("No PDF engines available - install weasyprint or reportlab")
    
    def convert_html_to_pdf(self, html_content: str, output_path: Path, 
                           title: Optional[str] = None) -> bool:
        """
        Convert HTML content to PDF.
        
        Args:
            html_content: HTML content to convert
            output_path: Output PDF file path
            title: Document title
            
        Returns:
            True if conversion successful
        """
        engine = self.config.conversion.pdf_engine
        
        if engine == 'weasyprint' and 'weasyprint' in self.engines:
            return self._convert_with_weasyprint(html_content, output_path, title)
        elif engine == 'reportlab' and 'reportlab' in self.engines:
            return self._convert_with_reportlab(html_content, output_path, title)
        elif self.engines:
            # Use first available engine
            engine = self.engines[0]
            self._logger.info(f"Using {engine} engine (preferred engine not available)")
            if engine == 'weasyprint':
                return self._convert_with_weasyprint(html_content, output_path, title)
            else:
                return self._convert_with_reportlab(html_content, output_path, title)
        else:
            self._logger.error("No PDF conversion engines available")
            return False
    
    def _convert_with_weasyprint(self, html_content: str, output_path: Path, 
                                title: Optional[str] = None) -> bool:
        """Convert HTML to PDF using WeasyPrint."""
        try:
            # Create CSS for styling
            css_content = self._generate_css()
            
            # Wrap HTML with proper structure
            full_html = self._wrap_html_content(html_content, title)
            
            # Convert to PDF
            html_doc = HTML(string=full_html)
            css_doc = CSS(string=css_content)
            
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            html_doc.write_pdf(str(output_path), stylesheets=[css_doc])
            
            self._logger.info(f"PDF created successfully: {output_path}")
            return True
            
        except Exception as e:
            self._logger.error(f"WeasyPrint conversion failed: {e}")
            return False
    
    def _convert_with_reportlab(self, html_content: str, output_path: Path,
                               title: Optional[str] = None) -> bool:
        """Convert HTML to PDF using ReportLab (simplified HTML support)."""
        try:
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create PDF document
            doc = SimpleDocTemplate(str(output_path), pagesize=A4)
            story = []
            
            # Get styles
            styles = getSampleStyleSheet()
            
            # Add title if provided
            if title:
                title_style = ParagraphStyle(
                    'CustomTitle',
                    parent=styles['Title'],
                    fontSize=18,
                    spaceAfter=30,
                )
                story.append(Paragraph(title, title_style))
            
            # Convert HTML to ReportLab elements (simplified)
            # This is a basic implementation - for full HTML support, use WeasyPrint
            plain_text = self._strip_html_tags(html_content)
            paragraphs = plain_text.split('\n\n')
            
            for para in paragraphs:
                if para.strip():
                    story.append(Paragraph(para.strip(), styles['Normal']))
                    story.append(Spacer(1, 0.2*inch))
            
            # Build PDF
            doc.build(story)
            
            self._logger.info(f"PDF created successfully: {output_path}")
            return True
            
        except Exception as e:
            self._logger.error(f"ReportLab conversion failed: {e}")
            return False
    
    def _generate_css(self) -> str:
        """Generate CSS for PDF styling."""
        config = self.config.conversion
        
        return f"""
        @page {{
            size: {config.pdf_page_size};
            margin: {config.pdf_margin}mm;
        }}
        
        body {{
            font-family: "{config.font_family}", serif;
            font-size: {config.font_size}pt;
            line-height: {config.line_height};
            color: #333;
        }}
        
        h1, h2, h3, h4, h5, h6 {{
            font-weight: bold;
            margin-top: 1.5em;
            margin-bottom: 0.5em;
        }}
        
        h1 {{ font-size: 2em; }}
        h2 {{ font-size: 1.5em; }}
        h3 {{ font-size: 1.2em; }}
        
        p {{
            margin-bottom: 1em;
        }}
        
        code {{
            background-color: #f5f5f5;
            padding: 2px 4px;
            border-radius: 3px;
            font-family: "Courier New", monospace;
        }}
        
        pre {{
            background-color: #f5f5f5;
            padding: 10px;
            border-radius: 5px;
            overflow-x: auto;
            font-family: "Courier New", monospace;
        }}
        
        table {{
            border-collapse: collapse;
            width: 100%;
            margin-bottom: 1em;
        }}
        
        th, td {{
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }}
        
        th {{
            background-color: #f2f2f2;
            font-weight: bold;
        }}
        
        blockquote {{
            border-left: 4px solid #ddd;
            margin: 0;
            padding-left: 16px;
            font-style: italic;
        }}
        """
    
    def _wrap_html_content(self, content: str, title: Optional[str] = None) -> str:
        """Wrap HTML content with proper document structure."""
        title_tag = f"<title>{title}</title>" if title else ""
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            {title_tag}
        </head>
        <body>
            {content}
        </body>
        </html>
        """
    
    def _strip_html_tags(self, html_content: str) -> str:
        """Strip HTML tags for plain text conversion."""
        # Simple HTML tag removal
        clean = re.compile('<.*?>')
        return re.sub(clean, '', html_content)


class MarkdownService:
    """
    Main service for markdown processing and PDF conversion.
    
    Coordinates markdown processing, content analysis, and PDF generation
    for synchronization with reMarkable devices.
    """
    
    def __init__(self, config: Optional[Any] = None):
        """
        Initialize markdown service.
        
        Args:
            config: Application configuration
        """
        self._logger = get_logger()
        self.config = config or get_config()
        
        self.processor = MarkdownProcessor(config)
        self.pdf_converter = PDFConverter(config)
        
        # File extensions
        self.markdown_extensions = {'.md', '.markdown', '.mdown', '.mkd', '.txt'}
        
        # ReMarkable service for upload integration
        self._remarkable_service = None
    
    def is_markdown_file(self, file_path: Path) -> bool:
        """
        Check if a file is a markdown file.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file is markdown
        """
        return file_path.suffix.lower() in self.markdown_extensions
    
    def process_markdown_file(self, input_path: Path, output_dir: Path,
                            upload_to_remarkable: bool = False,
                            title_override: Optional[str] = None) -> Optional[Path]:
        """
        Process a markdown file and convert to PDF.
        
        Args:
            input_path: Input markdown file
            output_dir: Output directory for PDF
            upload_to_remarkable: Whether to upload to ReMarkable after conversion
            title_override: Override title for the document
            
        Returns:
            Path to generated PDF if successful
        """
        if not input_path.exists():
            self._logger.error(f"Input file does not exist: {input_path}")
            return None
        
        if not self.is_markdown_file(input_path):
            self._logger.warning(f"File is not a markdown file: {input_path}")
            return None
        
        try:
            # Read markdown content
            with open(input_path, 'r', encoding='utf-8') as f:
                markdown_content = f.read()
            
            # Extract metadata
            metadata = self.processor.extract_metadata(markdown_content)
            title = title_override or metadata.get('title', input_path.stem)
            
            # Process markdown to HTML
            html_content = self.processor.process_markdown_content(markdown_content)
            
            # Generate output path
            output_path = output_dir / f"{input_path.stem}.pdf"
            
            # Convert to PDF
            if self.pdf_converter.convert_html_to_pdf(html_content, output_path, title):
                self._logger.info(f"Successfully processed: {input_path} -> {output_path}")
                
                # Upload to ReMarkable if requested
                if upload_to_remarkable:
                    return self.upload_pdf_to_remarkable(output_path, title)
                
                return output_path
            else:
                self._logger.error(f"Failed to convert to PDF: {input_path}")
                return None
                
        except Exception as e:
            self._logger.error(f"Error processing markdown file {input_path}: {e}")
            return None
    
    def batch_process_directory(self, input_dir: Path, output_dir: Path) -> List[Path]:
        """
        Process all markdown files in a directory.
        
        Args:
            input_dir: Input directory containing markdown files
            output_dir: Output directory for PDFs
            
        Returns:
            List of successfully generated PDF paths
        """
        if not input_dir.exists():
            self._logger.error(f"Input directory does not exist: {input_dir}")
            return []
        
        # Find all markdown files
        markdown_files = []
        for ext in self.markdown_extensions:
            markdown_files.extend(input_dir.glob(f"**/*{ext}"))
        
        if not markdown_files:
            self._logger.info(f"No markdown files found in: {input_dir}")
            return []
        
        self._logger.info(f"Found {len(markdown_files)} markdown files to process")
        
        # Process each file
        generated_pdfs = []
        for md_file in markdown_files:
            # Preserve directory structure in output
            rel_path = md_file.relative_to(input_dir)
            output_subdir = output_dir / rel_path.parent
            output_subdir.mkdir(parents=True, exist_ok=True)
            
            pdf_path = self.process_markdown_file(md_file, output_subdir)
            if pdf_path:
                generated_pdfs.append(pdf_path)
        
        self._logger.info(f"Successfully processed {len(generated_pdfs)} files")
        return generated_pdfs
    
    def get_file_info(self, file_path: Path) -> Dict[str, Any]:
        """
        Get information about a markdown file.
        
        Args:
            file_path: Path to markdown file
            
        Returns:
            Dictionary containing file information
        """
        if not file_path.exists():
            return {}
        
        try:
            stat_info = file_path.stat()
            
            info = {
                'path': str(file_path),
                'name': file_path.name,
                'size': stat_info.st_size,
                'modified': datetime.fromtimestamp(stat_info.st_mtime),
                'is_markdown': self.is_markdown_file(file_path)
            }
            
            if self.is_markdown_file(file_path):
                # Read content for analysis
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                metadata = self.processor.extract_metadata(content)
                info.update(metadata)
                
                # Add content statistics
                info['word_count'] = len(content.split())
                info['line_count'] = len(content.split('\n'))
                info['char_count'] = len(content)
            
            return info
            
        except Exception as e:
            self._logger.error(f"Error getting file info for {file_path}: {e}")
            return {'error': str(e)}
    
    def _get_remarkable_service(self):
        """Get ReMarkable service instance with lazy loading."""
        if self._remarkable_service is None:
            self._remarkable_service = get_remarkable_service()
        return self._remarkable_service
    
    def upload_pdf_to_remarkable(self, pdf_path: Path, title: Optional[str] = None) -> Optional[str]:
        """
        Upload a PDF file to ReMarkable device with duplicate checking.
        
        Args:
            pdf_path: Path to PDF file
            title: Document title (defaults to filename without extension)
            
        Returns:
            Document UUID if successful, None otherwise
        """
        if not pdf_path.exists():
            self._logger.error(f"PDF file does not exist: {pdf_path}")
            return None
        
        try:
            remarkable_service = self._get_remarkable_service()
            if title is None:
                title = pdf_path.stem
            
            # Use add_with_metadata_if_new for duplicate checking
            document_uuid = remarkable_service.add_with_metadata_if_new(pdf_path, title)
            
            if document_uuid:
                self._logger.info(f"Successfully uploaded PDF to ReMarkable: {title} (UUID: {document_uuid})")
                return document_uuid
            else:
                self._logger.error(f"Failed to upload PDF to ReMarkable: {title}")
                return None
                
        except Exception as e:
            self._logger.error(f"Error uploading PDF to ReMarkable: {e}")
            return None
    
    def process_and_upload_markdown(self, input_path: Path, output_dir: Path, 
                                   title_override: Optional[str] = None) -> Optional[str]:
        """
        Complete workflow: convert markdown to PDF and upload to ReMarkable.
        
        Args:
            input_path: Input markdown file
            output_dir: Output directory for PDF
            title_override: Override title for the document
            
        Returns:
            Document UUID if successful, None otherwise
        """
        # First convert to PDF
        pdf_path = self.process_markdown_file(input_path, output_dir, 
                                            upload_to_remarkable=False, 
                                            title_override=title_override)
        
        if not pdf_path:
            return None
        
        # Then upload to ReMarkable
        title = title_override or input_path.stem
        document_uuid = self.upload_pdf_to_remarkable(pdf_path, title)
        
        return document_uuid
    
    def check_document_exists_on_remarkable(self, title: str) -> Optional[str]:
        """
        Check if a document with the given title exists on ReMarkable.
        
        Args:
            title: Document title to search for
            
        Returns:
            Document UUID if found, None otherwise
        """
        try:
            remarkable_service = self._get_remarkable_service()
            return remarkable_service.hash_from_title(title)
        except Exception as e:
            self._logger.error(f"Error checking document existence: {e}")
            return None
    
    def get_last_read_document_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about the last read document on ReMarkable.
        
        Returns:
            Document information dictionary if found, None otherwise
        """
        try:
            remarkable_service = self._get_remarkable_service()
            last_uuid = remarkable_service.last_read_document()
            
            if last_uuid:
                return remarkable_service.get_document_info(last_uuid)
            
            return None
        except Exception as e:
            self._logger.error(f"Error getting last read document info: {e}")
            return None
    
    def batch_process_and_upload(self, input_dir: Path, output_dir: Path) -> Dict[str, Any]:
        """
        Process all markdown files in a directory and upload to ReMarkable.
        
        Args:
            input_dir: Input directory containing markdown files
            output_dir: Output directory for PDFs
            
        Returns:
            Dictionary with processing results and statistics
        """
        if not input_dir.exists():
            self._logger.error(f"Input directory does not exist: {input_dir}")
            return {"error": "Input directory not found", "processed": [], "failed": []}
        
        # Find all markdown files
        markdown_files = []
        for ext in self.markdown_extensions:
            markdown_files.extend(input_dir.glob(f"**/*{ext}"))
        
        if not markdown_files:
            self._logger.info(f"No markdown files found in: {input_dir}")
            return {"processed": [], "failed": [], "skipped": []}
        
        self._logger.info(f"Found {len(markdown_files)} markdown files to process and upload")
        
        processed = []
        failed = []
        skipped = []
        
        # Process each file
        for md_file in markdown_files:
            try:
                # Preserve directory structure in output
                rel_path = md_file.relative_to(input_dir)
                output_subdir = output_dir / rel_path.parent
                output_subdir.mkdir(parents=True, exist_ok=True)
                
                title = md_file.stem
                
                # Check if document already exists on ReMarkable
                existing_uuid = self.check_document_exists_on_remarkable(title)
                if existing_uuid:
                    self._logger.info(f"Document '{title}' already exists on ReMarkable (UUID: {existing_uuid})")
                    skipped.append({
                        "file": str(md_file),
                        "title": title,
                        "uuid": existing_uuid,
                        "reason": "Already exists on device"
                    })
                    continue
                
                # Process and upload
                document_uuid = self.process_and_upload_markdown(md_file, output_subdir, title)
                
                if document_uuid:
                    processed.append({
                        "file": str(md_file),
                        "title": title,
                        "uuid": document_uuid,
                        "status": "uploaded"
                    })
                else:
                    failed.append({
                        "file": str(md_file),
                        "title": title,
                        "error": "Processing or upload failed"
                    })
                    
            except Exception as e:
                self._logger.error(f"Error processing {md_file}: {e}")
                failed.append({
                    "file": str(md_file),
                    "title": md_file.stem,
                    "error": str(e)
                })
        
        results = {
            "processed": processed,
            "failed": failed,
            "skipped": skipped,
            "total_files": len(markdown_files),
            "success_count": len(processed),
            "fail_count": len(failed),
            "skip_count": len(skipped)
        }
        
        self._logger.info(f"Batch processing complete. Processed: {len(processed)}, Failed: {len(failed)}, Skipped: {len(skipped)}")
        return results


# Global service instance
_global_markdown_service: Optional[MarkdownService] = None


def get_markdown_service() -> MarkdownService:
    """
    Get the global markdown service instance.
    
    Returns:
        Global MarkdownService instance
    """
    global _global_markdown_service
    if _global_markdown_service is None:
        _global_markdown_service = MarkdownService()
    return _global_markdown_service


def init_markdown_service(config: Optional[Any] = None) -> MarkdownService:
    """
    Initialize the global markdown service.
    
    Args:
        config: Application configuration
        
    Returns:
        Initialized MarkdownService instance
    """
    global _global_markdown_service
    _global_markdown_service = MarkdownService(config)
    return _global_markdown_service