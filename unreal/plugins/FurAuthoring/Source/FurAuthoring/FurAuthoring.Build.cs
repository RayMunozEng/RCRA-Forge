using UnrealBuildTool;
using System.IO;
public class FurAuthoring : ModuleRules
{
    public FurAuthoring(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "ProceduralMeshComponent" });
        PrivateDependencyModuleNames.AddRange(new[] { "Projects", "RenderCore", "RHI", "Renderer" });
        PrivateIncludePaths.Add(Path.Combine(EngineDirectory, "Source/Runtime/Renderer/Private"));
        PrivateIncludePaths.Add(Path.Combine(EngineDirectory, "Source/Runtime/Renderer/Internal"));
        string ShaderDir = Path.GetFullPath(Path.Combine(ModuleDirectory, "../../Shaders")).Replace('\\', '/');
        PrivateDefinitions.Add("FUR_AUTHORING_SOURCE_SHADER_DIR=TEXT(\"" + ShaderDir + "\")");
    }
}
