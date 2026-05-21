import http from './index'

export function getPlans(params) { return http.get('/plans', { params }) }
export function getPlan(id) { return http.get(`/plans/${id}`) }
export function createPlan(data) { return http.post('/plans', data) }
export function updatePlan(id, data) { return http.put(`/plans/${id}`, data) }
export function deletePlan(id) { return http.delete(`/plans/${id}`) }
export function issuePlan(id) { return http.post(`/plans/${id}/issue`) }

export function addDimension(planId, data) { return http.post(`/plans/${planId}/dimensions`, data) }
export function updateDimension(id, data) { return http.put(`/dimensions/${id}`, data) }
export function deleteDimension(id) { return http.delete(`/dimensions/${id}`) }

export function addAssessmentDim(dimId, data) { return http.post(`/dimensions/${dimId}/assessment-dims`, data) }
export function updateAssessmentDim(id, data) { return http.put(`/assessment-dims/${id}`, data) }
export function deleteAssessmentDim(id) { return http.delete(`/assessment-dims/${id}`) }

export function setAssessorUnits(planId, unitIds) { return http.put(`/plans/${planId}/assessor-units`, { unit_ids: unitIds }) }

export function createGroup(planId, data) { return http.post(`/plans/${planId}/groups`, data) }
export function updateGroup(id, data) { return http.put(`/groups/${id}`, data) }
export function deleteGroup(id) { return http.delete(`/groups/${id}`) }
export function batchDeleteGroups(ids) { return http.post('/groups/batch-delete', { ids }) }
export function exportGroups(planId) { return http.get(`/plans/${planId}/groups/export`, { responseType: 'blob' }) }
export function importGroups(planId, formData) { return http.post(`/plans/${planId}/groups/import`, formData) }

export function getUnitsTree() { return http.get('/units-tree') }
