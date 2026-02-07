import BuilderAgentNode from './BuilderAgentNode'
import BuilderPersonaNode from './BuilderPersonaNode'
import BuilderChannelNode from './BuilderChannelNode'
import BuilderSkillNode from './BuilderSkillNode'
import BuilderToolNode from './BuilderToolNode'
import BuilderSentinelNode from './BuilderSentinelNode'
import BuilderKnowledgeNode from './BuilderKnowledgeNode'
import BuilderMemoryNode from './BuilderMemoryNode'

export const builderNodeTypes = {
  'builder-agent': BuilderAgentNode,
  'builder-persona': BuilderPersonaNode,
  'builder-channel': BuilderChannelNode,
  'builder-skill': BuilderSkillNode,
  'builder-tool': BuilderToolNode,
  'builder-sentinel': BuilderSentinelNode,
  'builder-knowledge': BuilderKnowledgeNode,
  'builder-memory': BuilderMemoryNode,
}

export { BuilderAgentNode, BuilderPersonaNode, BuilderChannelNode, BuilderSkillNode, BuilderToolNode, BuilderSentinelNode, BuilderKnowledgeNode, BuilderMemoryNode }
