using UnrealBuildTool;
public class FurValidationEditorTarget : TargetRules
{
 public FurValidationEditorTarget(TargetInfo Target) : base(Target)
 {
  Type = TargetType.Editor; DefaultBuildSettings = BuildSettingsVersion.Latest;
  IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
  ExtraModuleNames.Add("FurValidation");
 }
}
