#include "FurViewportProbe.h"
#include "FurDenoise.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"
#include "RenderingThread.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
BEGIN_SHADER_PARAMETER_STRUCT(FFurFilterTestReadback,)
    RDG_TEXTURE_ACCESS(Output,ERHIAccess::CopySrc)
END_SHADER_PARAMETER_STRUCT()
FString UFurViewportProbe::ValidateFurDenoiseGPU()
{
    TArray<FLinearColor> Samples;
    bool bInputGuard=false;
    ENQUEUE_RENDER_COMMAND(FurFilterTest)([&](FRHICommandListImmediate& RHICmdList)
    {
        FRDGBuilder Graph(RHICmdList);
        bInputGuard=AddRecoveredFurDenoisePass(Graph,FFurDenoiseInputs())==nullptr;
        for(int Case=0;Case<6;++Case)
        {
            auto Make=[&](const TCHAR* Name,FLinearColor Clear)
            {
                auto* T=Graph.CreateTexture(FRDGTextureDesc::Create2D(FIntPoint(128,64),PF_A32B32G32R32F,
                    FClearValueBinding::None,TexCreate_ShaderResource|TexCreate_UAV|TexCreate_RenderTargetable),Name);
                AddClearUAVPass(Graph,Graph.CreateUAV(T),Clear);return T;
            };
            FFurDenoiseInputs Inputs;
            Inputs.SceneColor=Make(TEXT("Test.Color"),Case<2?FLinearColor(.31,.2,.1,1):FLinearColor(1,0,0,1));
            Inputs.StrandDepth=Make(TEXT("Test.StrandDepth"),FLinearColor(1,0,0,.01));
            Inputs.NormalMask=Make(TEXT("Test.NormalMask"),FLinearColor(0,1,0,Case==1?0:1));
            if(Case>=2)AddClearRenderTargetPass(Graph,Inputs.SceneColor,FLinearColor(0,0,1,1),FIntRect(64,0,128,64));
            if(Case==3)AddClearRenderTargetPass(Graph,Inputs.StrandDepth,FLinearColor(1,0,0,.001),FIntRect(64,0,128,64));
            if(Case==4)AddClearRenderTargetPass(Graph,Inputs.NormalMask,FLinearColor(0,1,0,0),FIntRect(64,0,128,64));
            Inputs.ActiveTiles=Graph.CreateTexture(FRDGTextureDesc::Create2D(FIntPoint(16,8),PF_R32_UINT,
                FClearValueBinding::None,TexCreate_ShaderResource|TexCreate_UAV),TEXT("Test.Tiles"));
            AddClearUAVPass(Graph,Graph.CreateUAV(Inputs.ActiveTiles),uint32(Case==5?0:1));
            auto* P=Graph.AllocParameters<FFurFilterTestReadback>();
            P->Output=AddRecoveredFurDenoisePass(Graph,Inputs);
            if(!P->Output)continue;
            Graph.AddPass(RDG_EVENT_NAME("Fur.FilterTestReadback"),P,ERDGPassFlags::Readback,
                [P,&Samples](FRHICommandListImmediate& Cmd)
                {
                    TArray<FLinearColor> Pixels;FReadSurfaceDataFlags Flags(RCM_MinMax);Flags.SetLinearToGamma(false);
                    Cmd.ReadSurfaceData(P->Output->GetRHI(),FIntRect(63,32,65,33),Pixels,Flags);
                    Samples.Append(Pixels);
                });
        }
        Graph.Execute();
    });
    FlushRenderingCommands();
    TSharedRef<FJsonObject> Report=MakeShared<FJsonObject>();
    Report->SetBoolField(TEXT("invalid_inputs_rejected"),bInputGuard);
    TArray<TSharedPtr<FJsonValue>> Values;
    for(const auto& P:Samples)
    {
        TArray<TSharedPtr<FJsonValue>> C;
        for(float V:{P.R,P.G,P.B,P.A})C.Add(MakeShared<FJsonValueNumber>(V));
        Values.Add(MakeShared<FJsonValueArray>(C));
    }
    Report->SetArrayField(TEXT("pixels"),Values);
    FString Json;FJsonSerializer::Serialize(Report,TJsonWriterFactory<>::Create(&Json));return Json;
}
