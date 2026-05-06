import { useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';

import { api } from '@/lib/api';
import type { ApiError } from '@/lib/api';
import type { AnalyzeAccepted, AnalyzeRequest } from '@/lib/types';

export function useStartAnalysis(opts?: {
  onSuccess?: (data: AnalyzeAccepted, vars: AnalyzeRequest) => void;
}) {
  return useMutation<AnalyzeAccepted, ApiError, AnalyzeRequest>({
    mutationFn: api.startAnalysis,
    onSuccess: (data, vars) => {
      opts?.onSuccess?.(data, vars);
    },
    onError: (err) => {
      toast.error(`Submission failed: ${err.detail}`);
    },
  });
}
