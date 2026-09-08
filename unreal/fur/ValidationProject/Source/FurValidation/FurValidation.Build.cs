using UnrealBuildTool;
public class FurValidation : ModuleRules
{
 public FurValidation(ReadOnlyTargetRules Target) : base(Target)
 {
  PrivateIncludePaths.Add(System.IO.Path.Combine(EngineDirectory,"Source/Runtime/Renderer/Private"));
  PrivateIncludePaths.Add(System.IO.Path.Combine(EngineDirectory,"Source/Runtime/Renderer/Internal"));
  PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
  PublicDependencyModuleNames.AddRange(new[] {"Core", "CoreUObject", "Engine"});
  if (Target.bBuildEditor) PrivateDependencyModuleNames.AddRange(new[] {"FurAuthoring", "UnrealEd", "RenderCore", "RHI", "Json", "Renderer"});
 }
}
