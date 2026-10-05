export type Category = {
  id: number;
  name: string;
  created_at: string;
  is_system: boolean;
  document_count: number;
};

export type User = {
  id: number;
  email: string;
};

export type CategoryBrief = Pick<Category, 'id' | 'name' | 'is_system'>;

export type ScanMode = 'color' | 'black_and_white';

export type ScanCorners = {
  top_left: [number, number];
  top_right: [number, number];
  bottom_right: [number, number];
  bottom_left: [number, number];
};

export type Document = {
  id: number;
  title: string;
  category_id: number;
  category: CategoryBrief;
  created_at: string;
  original_image_url: string;
  scanned_image_url: string;
  bw_image_url: string | null;
  ocr_text: string | null;
  ocr_error: string | null;
  classification_error: string | null;
  processing_status: 'uploaded' | 'processing' | 'complete' | 'needs_review' | 'failed';
  classification_confidence: number | null;
  detected_corners: ScanCorners | null;
  scan_confidence: number | null;
  scan_debug: Record<string, unknown> | null;
  scan_mode: ScanMode;
};

export type SearchResult = {
  document: Document;
  score: number;
};

export type SearchResponse = {
  query: string;
  results: SearchResult[];
};
