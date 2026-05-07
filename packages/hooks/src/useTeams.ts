import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import type { Team } from "@aigw/contracts";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

async function fetchTeams(): Promise<Team[]> {
  const res = await fetch(`${BASE_URL}/api/v1/teams`);
  if (!res.ok) {
    throw new Error(`Failed to fetch teams: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<Team[]>;
}

/**
 * React Query hook that fetches all teams from GET /api/v1/teams.
 */
export function useTeams(): UseQueryResult<Team[]> {
  return useQuery<Team[]>({
    queryKey: ["teams"],
    queryFn: fetchTeams,
  });
}
