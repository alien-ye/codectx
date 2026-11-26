# Context for: Compose processing steps so one output feeds the next

## AgentExecutorIterator._process_next_step_output  (method)  libs/langchain/langchain_classic/agents/agent_iterator.py:317
signature: (
        self,
        next_step_output: AgentFinish | list[tuple[AgentAction, str]],
        run_manager: CallbackManagerForChainRun,
    ) -> AddableDict
doc: Process the output of the next step.

        Process the output of the next step,
        handling AgentFinish and tool return cases.
        
```
    def _process_next_step_output(
        self,
        next_step_output: AgentFinish | list[tuple[AgentAction, str]],
        run_manager: CallbackManagerForChainRun,
    ) -> AddableDict:
        """Process the output of the next step.

        Process the output of the next step,
        handling AgentFinish and tool return cases.
        """
        logger.debug("Processing output of Agent loop step")
        if isinstance(next_step_output, AgentFinish):
            logger.debug(
                "Hit AgentFinish: _return -> on_chain_end -> run final output logic",
            )
            return self._return(next_step_output, run_manager=run_manager)

        self.intermediate_steps.extend(next_step_output)
        logger.debug("Updated intermediate_steps with step output")

        # Check for tool return
        if len(next_step_output) == 1:
            next_step_action = next_step_output[0]
            tool_return = self.agent_executor._get_tool_return(next_step_action)  # noqa: SLF001
            if tool_return is not None:
                return self._return(tool_return, run_manager=run_manager)

        return AddableDict(intermediate_step=next_step_output)
```

## NextStepOutput  (variable)  libs/langchain/langchain_classic/agents/agent.py:1008
```
NextStepOutput = list[AgentFinish | AgentAction | AgentStep]
```

## AgentExecutorIterator._aprocess_next_step_output  (method)  libs/langchain/langchain_classic/agents/agent_iterator.py:346
signature: (
        self,
        next_step_output: AgentFinish | list[tuple[AgentAction, str]],
        run_manager: AsyncCallbackManagerForChainRun,
    ) -> AddableDict
doc: Process the output of the next async step.

        Process the output of the next async step,
        handling AgentFinish and tool return cases.
        
```
    async def _aprocess_next_step_output(
        self,
        next_step_output: AgentFinish | list[tuple[AgentAction, str]],
        run_manager: AsyncCallbackManagerForChainRun,
    ) -> AddableDict:
        """Process the output of the next async step.

        Process the output of the next async step,
        handling AgentFinish and tool return cases.
        """
        logger.debug("Processing output of async Agent loop step")
        if isinstance(next_step_output, AgentFinish):
            logger.debug(
                "Hit AgentFinish: _areturn -> on_chain_end -> run final output logic",
            )
            return await self._areturn(next_step_output, run_manager=run_manager)

        self.intermediate_steps.extend(next_step_output)
        logger.debug("Updated intermediate_steps with step output")

        # Check for tool return
        if len(next_step_output) == 1:
            next_step_action = next_step_output[0]
            tool_return = self.agent_executor._get_tool_return(next_step_action)  # noqa: SLF001
            if tool_return is not None:
                return await self._areturn(tool_return, run_manager=run_manager)

        return AddableDict(intermediate_step=next_step_output)
```

## RouterOutputParser.next_inputs_type  (variable)  libs/langchain/langchain_classic/chains/router/llm_router.py:172
```
    next_inputs_type: type = str
```

## Route.next_inputs  (variable)  libs/langchain/langchain_classic/chains/router/base.py:24
```
    next_inputs: dict[str, Any]
```

