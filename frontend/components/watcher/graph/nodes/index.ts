/**
 * Node type registry for React Flow
 * Phase 4: Added ProjectNode
 * Phase 5: Added UserNode, SkillNode, KnowledgeNode
 * Phase 6: Added KnowledgeSummaryNode
 * Phase 7: Added SkillCategoryNode for skill grouping
 * Phase 9: Added SkillProviderNode for showing available providers as children of skills
 */

import AgentNode from './AgentNode'
import ChannelNode from './ChannelNode'
import ProjectNode from './ProjectNode'
import UserNode from './UserNode'
import SkillNode from './SkillNode'
import KnowledgeNode from './KnowledgeNode'
import KnowledgeSummaryNode from './KnowledgeSummaryNode'
import SkillCategoryNode from './SkillCategoryNode'
import SkillProviderNode from './SkillProviderNode'

export const nodeTypes = {
  agent: AgentNode,
  channel: ChannelNode,
  project: ProjectNode,
  user: UserNode,
  skill: SkillNode,
  knowledge: KnowledgeNode,
  'knowledge-summary': KnowledgeSummaryNode,
  'skill-category': SkillCategoryNode,
  'skill-provider': SkillProviderNode,
}

export { AgentNode, ChannelNode, ProjectNode, UserNode, SkillNode, KnowledgeNode, KnowledgeSummaryNode, SkillCategoryNode, SkillProviderNode }
