import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as projectsApi from '@/api/projects'
import * as documentsApi from '@/api/documents'
import type { DocumentItem, Project, ProjectPayload } from '@/types'

export const useProjectsStore = defineStore('projects', () => {
  const projects = ref<Project[]>([])
  const currentProject = ref<Project | null>(null)
  const documents = ref<DocumentItem[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchProjects(q?: string) {
    loading.value = true
    error.value = null
    try {
      projects.value = await projectsApi.listProjects(q ? { q } : undefined)
    } catch (err: unknown) {
      error.value = 'Failed to load projects'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function fetchProject(id: number) {
    loading.value = true
    error.value = null
    try {
      currentProject.value = await projectsApi.getProject(id)
      documents.value = await documentsApi.listDocuments(id)
      return currentProject.value
    } catch (err: unknown) {
      error.value = 'Failed to load project'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function create(payload: ProjectPayload) {
    const project = await projectsApi.createProject(payload)
    projects.value.unshift(project)
    return project
  }

  async function update(id: number, payload: Partial<ProjectPayload>) {
    const project = await projectsApi.updateProject(id, payload)
    currentProject.value = project
    const idx = projects.value.findIndex((p) => p.id === id)
    if (idx >= 0) projects.value[idx] = project
    return project
  }

  async function archive(id: number) {
    await projectsApi.archiveProject(id)
    const idx = projects.value.findIndex((p) => p.id === id)
    if (idx >= 0) {
      projects.value[idx] = { ...projects.value[idx], status: 'archived' }
    }
    if (currentProject.value?.id === id) {
      currentProject.value = { ...currentProject.value, status: 'archived' }
    }
  }

  async function remove(id: number) {
    await projectsApi.archiveProject(id, true)
    projects.value = projects.value.filter((p) => p.id !== id)
    if (currentProject.value?.id === id) currentProject.value = null
  }

  async function upload(
    projectId: number,
    file: File,
    revisionLabel?: string,
    notes?: string,
    onProgress?: (percent: number) => void,
  ) {
    const doc = await documentsApi.uploadDocument(projectId, file, revisionLabel, notes, onProgress)
    documents.value.unshift(doc)
    if (currentProject.value?.id === projectId) {
      currentProject.value.document_count += 1
    }
    return doc
  }

  async function removeDocument(documentId: number) {
    await documentsApi.deleteDocument(documentId)
    documents.value = documents.value.filter((d) => d.id !== documentId)
    if (currentProject.value) {
      currentProject.value.document_count = Math.max(0, currentProject.value.document_count - 1)
    }
  }

  return {
    projects,
    currentProject,
    documents,
    loading,
    error,
    fetchProjects,
    fetchProject,
    create,
    update,
    archive,
    remove,
    upload,
    removeDocument,
  }
})
