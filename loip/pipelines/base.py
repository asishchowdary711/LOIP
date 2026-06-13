from abc import ABC, abstractmethod

class BasePipeline(ABC):
    @abstractmethod
    async def execute(self, *args, **kwargs):
        pass
        
    def validate_inputs(self, *args, **kwargs):
        pass
