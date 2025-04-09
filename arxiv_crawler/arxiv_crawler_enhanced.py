import requests
import urllib.parse
import re
import os
import time
import argparse
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import feedparser
import json

def search_arxiv(title_query="", abstract_query="", category="", max_results=50, database_manager=None, skip_existing=True):
    """
    Search arXiv for papers matching the query and return a list of paper info
    
    Args:
        title_query (str): Query for title
        abstract_query (str): Query for abstract
        category (str): arXiv category
        max_results (int): Maximum number of NEW papers to return
        database_manager: DatabaseManager instance for checking existing papers
        skip_existing (bool): Whether to skip papers that exist in the database
        
    Returns:
        list: List of paper information dictionaries
    """
    base_url = "http://export.arxiv.org/api/query?"
    
    # 设置搜索参数
    batch_size = 50  # 每次API请求的论文数量
    max_search_attempts = 20  # 最大搜索次数，防止无限循环
    max_total_results = 1000  # 最大总搜索结果数，避免过多请求
    
    # Build search query
    search_terms = []
    if title_query:
        search_terms.append(f"ti:{title_query}")
    if abstract_query:
        search_terms.append(f"abs:{abstract_query}")
    if category:
        search_terms.append(f"cat:{category}")
    
    # If no specific fields were provided, search in all fields
    if not search_terms:
        # Use one of the queries as an all-fields search
        query = title_query or abstract_query
        if query:
            search_terms = [f"all:{query}"]
        else:
            raise ValueError("No search criteria provided")
    
    # Join search terms with AND
    search_query = " AND ".join(search_terms)
    
    # URL encode the query
    encoded_query = urllib.parse.quote(search_query)
    
    # 存储所有论文信息
    papers = []
    new_papers_count = 0
    
    # 分页搜索，直到找到足够的新论文或达到最大搜索限制
    for attempt in range(max_search_attempts):
        start_index = attempt * batch_size
        
        if start_index >= max_total_results:
            print(f"Reached maximum search limit of {max_total_results} results")
            break
            
        # 构建API请求URL
        params = f"search_query={encoded_query}&start={start_index}&max_results={batch_size}&sortBy=submittedDate&sortOrder=descending"
        
        print(f"Searching batch {attempt+1}: results {start_index} to {start_index+batch_size}")
        
        try:
            # 发送请求
            response = requests.get(base_url + params)
            
            # 解析响应
            feed = feedparser.parse(response.content)
            
            # 检查是否有结果
            if not feed.entries:
                print("No more results found")
                break
                
            # 处理这一批结果
            for entry in feed.entries:
                paper_id = entry.id.split('/abs/')[-1]
                
                # Extract the PDF link
                pdf_url = f"https://arxiv.org/pdf/{paper_id}.pdf"
                
                # Get categories
                categories = [tag['term'] for tag in entry.tags] if 'tags' in entry else []
                
                # Extract DOI if available
                doi = None
                if hasattr(entry, 'arxiv_doi'):
                    doi = entry.arxiv_doi
                elif hasattr(entry, 'doi'):
                    doi = entry.doi
                # Try to find DOI in the summary
                elif hasattr(entry, 'summary'):
                    doi_match = re.search(r'doi:\s*(10\.\d+/[^\s]+)', entry.summary, re.IGNORECASE)
                    if doi_match:
                        doi = doi_match.group(1)
                
                paper_info = {
                    'id': paper_id,
                    'title': entry.title,
                    'authors': [author.name for author in entry.authors],
                    'abstract': entry.summary,
                    'published': entry.published,
                    'updated': entry.updated,
                    'categories': categories,
                    'url': entry.link,
                    'pdf_url': pdf_url,
                    'doi': doi,
                    'already_exists': False  # 默认标记为不存在
                }
                
                # 检查是否已存在于数据库中
                if skip_existing and database_manager:
                    if check_if_paper_exists(paper_info, database_manager):
                        paper_info['already_exists'] = True
                        print(f"Paper already exists in database: {paper_id}")
                    else:
                        new_papers_count += 1
                        print(f"New paper found: {paper_id}")
                else:
                    new_papers_count += 1
                
                papers.append(paper_info)
            
            # 如果已经找到足够的新论文，可以提前停止
            if new_papers_count >= max_results:
                print(f"Found {new_papers_count} new papers, stopping search")
                break
                
            # 防止过快请求
            time.sleep(3)
            
        except Exception as e:
            print(f"Error searching arXiv: {str(e)}")
            break
    
    print(f"Search completed. Found {len(papers)} total papers, {new_papers_count} are new.")
    return papers

def download_pdf(paper_info, output_dir, progress_callback=None):
    """
    Download PDF and save to the specified directory
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Create a valid filename from the title
    filename = re.sub(r'[^\w\s-]', '', paper_info['title'])
    filename = re.sub(r'[-\s]+', '_', filename)
    
    # Append paper ID to ensure uniqueness
    filename = f"{filename}_{paper_info['id']}.pdf"
    filepath = os.path.join(output_dir, filename)
    
    # Check if already downloaded
    if os.path.exists(filepath):
        if progress_callback:
            progress_callback('skipped_existing', paper_info, filepath)
        print(f"File already exists: {filepath}")
        return filepath
    
    # Download the PDF
    try:
        if progress_callback:
            progress_callback('downloading', paper_info, None)
        
        response = requests.get(paper_info['pdf_url'], stream=True)
        
        # Get content length if available
        total_size = int(response.headers.get('content-length', 0))
        
        with open(filepath, 'wb') as f:
            if total_size > 0 and progress_callback:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        progress = min(100, int(downloaded * 100 / total_size))
                        progress_callback('downloading_progress', paper_info, progress)
            else:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        
        if progress_callback:
            progress_callback('download_complete', paper_info, filepath)
        
        return filepath
    except Exception as e:
        if progress_callback:
            progress_callback('download_error', paper_info, str(e))
        print(f"Error downloading {paper_info['id']}: {str(e)}")
        return None

def save_metadata(papers, output_dir, filename="papers_metadata"):
    """
    Save paper metadata to a CSV file
    """
    import csv
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    metadata_file = os.path.join(output_dir, f"{filename}.csv")
    
    fieldnames = ['id', 'title', 'authors', 'abstract', 'published', 'updated', 'categories', 'url', 'pdf_url', 'doi', 'already_exists']
    
    with open(metadata_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for paper in papers:
            # Convert lists to strings for CSV
            paper_row = paper.copy()
            paper_row['authors'] = ', '.join(paper['authors'])
            paper_row['categories'] = ', '.join(paper['categories'])
            writer.writerow(paper_row)
    
    # Also save as JSON for easier progress tracking
    json_file = os.path.join(output_dir, f"{filename}.json")
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)
    
    return metadata_file

def check_if_paper_exists(paper_info, database_manager=None):
    """
    Check if paper already exists in the database using DOI or arXiv ID
    
    Args:
        paper_info: Dictionary containing paper information
        database_manager: DatabaseManager instance for database checks
    
    Returns:
        bool: True if paper exists, False otherwise
    """
    if database_manager is None:
        return False
    
    # Check by DOI if available
    if paper_info.get('doi'):
        paper = database_manager.get_paper_by_doi(paper_info['doi'])
        if paper:
            return True
    
    # Check by arXiv ID
    if paper_info.get('id'):
        paper = database_manager.get_paper_by_arxiv_id(paper_info['id'])
        if paper:
            return True
    
    return False

def save_progress(output_dir, total, processed, skipped, completed, current_paper=None, status="in_progress"):
    """
    Save crawler progress information to a JSON file
    
    Args:
        output_dir: Directory to save progress file
        total: Total number of papers to process
        processed: Number of papers processed so far
        skipped: Number of papers skipped (already in database)
        completed: Number of papers successfully downloaded and saved
        current_paper: Current paper being processed (dict)
        status: Current status (in_progress, completed, error)
    """
    progress_file = os.path.join(output_dir, "crawler_progress.json")
    
    progress_data = {
        "total": total,
        "processed": processed,
        "skipped": skipped,
        "completed": completed,
        "percent_complete": int((processed / max(total, 1)) * 100),
        "status": status,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "current_paper": current_paper
    }
    
    with open(progress_file, 'w', encoding='utf-8') as f:
        json.dump(progress_data, f, ensure_ascii=False, indent=2)
    
    return progress_file

def main():
    parser = argparse.ArgumentParser(description='Download arXiv papers based on search criteria')
    parser.add_argument('--title', type=str, help='Search in title')
    parser.add_argument('--abstract', type=str, help='Search in abstract')
    parser.add_argument('--query', type=str, help='Search in all fields')
    parser.add_argument('--category', type=str, help='Filter by arXiv category (e.g., cs.AI, physics.optics)')
    parser.add_argument('--output', type=str, default='arxiv_papers', help='Output directory for downloaded papers')
    parser.add_argument('--max', type=int, default=10, help='Maximum number of papers to download')
    parser.add_argument('--metadata-only', action='store_true', help='Save metadata without downloading PDFs')
    parser.add_argument('--skip-existing', action='store_true', help='Skip papers that exist in the database')
    parser.add_argument('--database-check', action='store_true', help='Check if papers exist in database before downloading')
    args = parser.parse_args()
    
    # Ensure at least one search criterion is provided
    if not (args.title or args.abstract or args.query or args.category):
        parser.error("At least one search criterion (--title, --abstract, --query, or --category) is required")
    
    title_query = args.title or args.query
    abstract_query = args.abstract
    
    print(f"Searching arXiv for papers...")
    if title_query:
        print(f"Title contains: {title_query}")
    if abstract_query:
        print(f"Abstract contains: {abstract_query}")
    if args.category:
        print(f"Category: {args.category}")
    
    # Initialize database manager if checking for existing papers
    database_manager = None
    if args.database_check:
        try:
            import sys
            import os
            sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from database.db_utils import DatabaseManager
            database_manager = DatabaseManager()
            print("Database connection established for duplicate checking")
        except Exception as e:
            print(f"Warning: Could not initialize database manager for duplicate checking: {str(e)}")
            database_manager = None
    
    # 搜索论文，允许筛选已有论文
    papers = search_arxiv(
        title_query, 
        abstract_query, 
        args.category, 
        args.max, 
        database_manager, 
        args.skip_existing
    )
    
    if not papers:
        print("No papers found matching the criteria.")
        # Save empty progress for UI
        save_progress(args.output, 0, 0, 0, 0, None, "completed")
        return
    
    # 过滤掉已存在的论文
    new_papers = [p for p in papers if not p.get('already_exists', False)]
    skipped_papers = [p for p in papers if p.get('already_exists', False)]
    
    print(f"Found {len(papers)} papers, {len(new_papers)} are new, {len(skipped_papers)} already exist in database.")
    
    # 如果启用了跳过已有论文，只处理新论文
    papers_to_process = new_papers if args.skip_existing else papers
    
    # 检查是否有足够的新论文
    if len(papers_to_process) < args.max:
        print(f"Warning: Only found {len(papers_to_process)} new papers, less than requested {args.max}")
    
    # 如果没有新论文可处理，提前退出
    if not papers_to_process:
        print("No new papers to process.")
        save_progress(args.output, 0, 0, len(skipped_papers), 0, None, "completed")
        
        # 保存已跳过的论文元数据供参考
        if skipped_papers:
            metadata_file = save_metadata(skipped_papers, args.output, filename="skipped_papers_metadata")
            print(f"Saved skipped papers metadata to: {metadata_file}")
        
        return
    
    # 截取到最大数量
    papers_to_process = papers_to_process[:args.max]
    
    # Save metadata for papers to process
    metadata_file = save_metadata(papers_to_process, args.output)
    print(f"Saved metadata to: {metadata_file}")
    
    # Initialize progress counters
    total_papers = len(papers_to_process)
    processed_papers = 0
    skipped_papers_count = len(skipped_papers)
    completed_papers = 0
    
    # Initial progress
    save_progress(
        args.output, 
        total_papers, 
        processed_papers, 
        skipped_papers_count, 
        completed_papers, 
        None, 
        "in_progress"
    )
    
    if args.metadata_only:
        print("Metadata-only mode: skipping PDF downloads")
        save_progress(
            args.output, 
            total_papers, 
            total_papers, 
            skipped_papers_count, 
            total_papers, 
            None, 
            "completed"
        )
        return
    
    print("Starting download...")
    
    # Define progress callback for UI updates
    def progress_callback(event_type, paper, data):
        nonlocal processed_papers, skipped_papers_count, completed_papers
        
        if event_type == 'skipped_existing':
            skipped_papers_count += 1
        elif event_type == 'download_complete':
            completed_papers += 1
        
        # Update progress file on significant events
        if event_type in ['skipped_existing', 'download_complete', 'download_error']:
            save_progress(
                args.output, 
                total_papers,
                processed_papers,
                skipped_papers_count,
                completed_papers,
                paper,
                "in_progress"
            )
    
    for i, paper in enumerate(papers_to_process):
        processed_papers += 1
        
        try:
            print(f"Processing paper {i+1}/{len(papers_to_process)}: {paper['id']}")
            print(f"Title: {paper['title']}")
            print(f"Authors: {', '.join(paper['authors'])}")
            print(f"Categories: {', '.join(paper['categories'])}")
            
            filepath = download_pdf(paper, args.output, progress_callback)
            
            if filepath:
                print(f"Saved to: {filepath}")
                completed_papers += 1
            
            # Update progress after each paper
            save_progress(
                args.output,
                total_papers,
                processed_papers,
                skipped_papers_count, 
                completed_papers,
                paper,
                "in_progress"
            )
            
            # Add a small delay to avoid overwhelming the server
            time.sleep(1)
            
        except Exception as e:
            print(f"Error processing paper {paper['id']}: {str(e)}")
    
    # Final progress update
    save_progress(
        args.output,
        total_papers,
        processed_papers,
        skipped_papers_count,
        completed_papers,
        None,
        "completed"
    )
    
    print(f"Download complete. Files saved to {os.path.abspath(args.output)}")

if __name__ == "__main__":
    main() 