#include "Modules/ModuleManager.h"
#include "Misc/Paths.h"
#include "ShaderCore.h"

class FFurAuthoringModule : public IModuleInterface
{
public:
    virtual void StartupModule() override
    {
#if WITH_EDITOR
        FString ShaderDir = FPaths::Combine(FPaths::ProjectPluginsDir(), TEXT("FurAuthoring/Shaders"));
        if (!FPaths::DirectoryExists(ShaderDir))
            ShaderDir = FPaths::Combine(FPaths::EnginePluginsDir(), TEXT("FurAuthoring/Shaders"));
        // Additional plugin directories can stage their DLL in Project/Binaries.
        // The source build records its real shader root for that layout.
        if (!FPaths::DirectoryExists(ShaderDir)) ShaderDir = FUR_AUTHORING_SOURCE_SHADER_DIR;
        ShaderDir = FPaths::ConvertRelativePathToFull(ShaderDir);
        if (!FPaths::DirectoryExists(ShaderDir))
        {
            UE_LOG(LogTemp, Error, TEXT("Fur Authoring shaders missing; rebuild the plugin after moving it."));
            return;
        }
        AddShaderSourceDirectoryMapping(TEXT("/Plugin/FurAuthoring"),
            ShaderDir);
#endif
    }
};
IMPLEMENT_MODULE(FFurAuthoringModule, FurAuthoring)
