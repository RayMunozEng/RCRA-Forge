#include "MaterialExpressionFurSurfaceOutput.h"
#if WITH_EDITOR
#include "MaterialCompiler.h"
#endif
UMaterialExpressionFurSurfaceOutput::UMaterialExpressionFurSurfaceOutput(const FObjectInitializer& Initializer):Super(Initializer)
{
#if WITH_EDITORONLY_DATA
    bCollapsed=true;
    Outputs.Reset();
#endif
}
#if WITH_EDITOR
int32 UMaterialExpressionFurSurfaceOutput::Compile(FMaterialCompiler* Compiler,int32 OutputIndex)
{
    FExpressionInput* Input=GetInput(OutputIndex);
    if(!Input || !Input->GetTracedInput().Expression)
        return CompilerError(Compiler,TEXT("Fur Surface Data requires Normal and Strand"));
    return Compiler->CustomOutput(this,OutputIndex,Input->Compile(Compiler));
}
FExpressionInput* UMaterialExpressionFurSurfaceOutput::GetInput(int32 Index)
{ return Index==0?&Normal:Index==1?&Strand:nullptr; }
FName UMaterialExpressionFurSurfaceOutput::GetInputName(int32 Index) const
{ if(Index==0)return FName(TEXT("Normal")); if(Index==1)return FName(TEXT("Strand")); return NAME_None; }
void UMaterialExpressionFurSurfaceOutput::GetCaption(TArray<FString>& Captions) const
{ Captions.Add(TEXT("Fur Surface Data")); }
#endif
