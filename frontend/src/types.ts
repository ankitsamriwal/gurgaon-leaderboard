export interface LeaderboardEntry {
  rank: number;
  project_id: string;
  name: string;
  developer_name: string;
  locality: string;
  total_paise: number;
  bid_count: number;
}

export interface LeaderboardResponse {
  leader: { project_id: string; leader_since: string } | null;
  daily_topper: { project_id: string; last_24h_paise: number } | null;
  rankings: LeaderboardEntry[];
}

export interface BidItem {
  id: string;
  bidder_label: string | null;
  amount_paise: number;
  created_at: string;
}

export interface ProjectDetail {
  id: string;
  name: string;
  developer_name: string;
  locality: string;
  rera_number: string;
  rera_verified: boolean;
  project_url: string | null;
  is_verified_developer_listing: boolean;
  total_paise: number;
  bid_count: number;
  bids: { page: number; page_size: number; items: BidItem[] };
}

export interface CurrentUser {
  id: string;
  display_name: string;
}

export interface ApiError {
  error: { code: string; message: string };
}
