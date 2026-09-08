#include "FurDenoiseViewExtension.h"
#include "Engine/Engine.h"
#include "Misc/CoreDelegates.h"
#include "Modules/ModuleManager.h"
#include "Misc/Paths.h"
#include "Interfaces/IPluginManager.h"
#include "ShaderCore.h"

class FFurAuthoringModule : public IModuleInterface
{
public:
    virtual void StartupModule() override
    {
        const TSharedPtr<IPlugin> Plugin =
            IPluginManager::Get().FindPlugin(TEXT("FurAuthoring"));
        FString ShaderDir = Plugin.IsValid()
            ? FPaths::Combine(Plugin->GetBaseDir(), TEXT("Shaders"))
            : FString();
        if (ShaderDir.IsEmpty())
            ShaderDir = FPaths::Combine(FPaths::ProjectPluginsDir(), TEXT("FurAuthoring/Shaders"));
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
        if (GEngine)
            StartDenoiseViewExtension();
        else
            PostEngineInitHandle = FCoreDelegates::GetOnPostEngineInit().AddRaw(
                this, &FFurAuthoringModule::StartDenoiseViewExtension);
    }

    virtual void ShutdownModule() override
    {
        if (PostEngineInitHandle.IsValid())
        {
            FCoreDelegates::GetOnPostEngineInit().Remove(PostEngineInitHandle);
            PostEngineInitHandle.Reset();
        }
        FurAuthoring::StopDenoiseViewExtension();
    }

private:
    void StartDenoiseViewExtension()
    {
        if (PostEngineInitHandle.IsValid())
        {
            FCoreDelegates::GetOnPostEngineInit().Remove(PostEngineInitHandle);
            PostEngineInitHandle.Reset();
        }
        FurAuthoring::StartDenoiseViewExtension();
    }

    FDelegateHandle PostEngineInitHandle;
};
IMPLEMENT_MODULE(FFurAuthoringModule, FurAuthoring)
