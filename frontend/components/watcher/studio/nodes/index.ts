import BuilderAgentNode from './BuilderAgentNode'
import BuilderGroupNode from './BuilderGroupNode'
import BuilderPersonaNode from './BuilderPersonaNode'
import BuilderChannelNode from './BuilderChannelNode'
import BuilderSkillNode from './BuilderSkillNode'
import BuilderSkillProviderNode from './BuilderSkillProviderNode'
import BuilderToolNode from './BuilderToolNode'
import BuilderSentinelNode from './BuilderSentinelNode'
import BuilderKnowledgeNode from './BuilderKnowledgeNode'
import BuilderMemoryNode from './BuilderMemoryNode'

export const builderNodeTypes = {
  'builder-agent': BuilderAgentNode,
  'builder-group': BuilderGroupNode,
  'builder-persona': BuilderPersonaNode,
  'builder-channel': BuilderChannelNode,
  'builder-skill': BuilderSkillNode,
  'builder-skill-provider': BuilderSkillProviderNode,
  'builder-tool': BuilderToolNode,
  'builder-sentinel': BuilderSentinelNode,
  'builder-knowledge': BuilderKnowledgeNode,
  'builder-memory': BuilderMemoryNode,
}

export { BuilderAgentNode, BuilderGroupNode, BuilderPersonaNode, BuilderChannelNode, BuilderSkillNode, BuilderSkillProviderNode, BuilderToolNode, BuilderSentinelNode, BuilderKnowledgeNode, BuilderMemoryNode }
