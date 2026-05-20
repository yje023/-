import request from './index'

export function getDashboardOverview(planId = null) {
  const params = {}
  if (planId) params.plan_id = planId
  return request.get('/dashboard/overview', { params })
}
