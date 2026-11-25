import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client.ts'

export function documentKey(ownerId: string) {
  return ['documents', ownerId] as const
}

export function useDocuments(ownerId: string) {
  return useQuery({
    queryKey: documentKey(ownerId),
    queryFn: ({ signal }) => api.documents(signal),
  })
}
