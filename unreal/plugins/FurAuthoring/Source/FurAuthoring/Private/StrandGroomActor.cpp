#include "StrandGroomActor.h"

#include "Materials/MaterialInstanceDynamic.h"
#include "Components/PoseableMeshComponent.h"
#include "Components/SkinnedMeshComponent.h"
#include "Engine/SkinnedAsset.h"
#include "Engine/SkeletalMesh.h"
#include "StrandGroomAsset.h"

namespace
{
// Exact 64xfloat4 lookup table embedded in CS_ModelStrandSimulateWind at
// retail capture event 24762. Entries 0..2 are the vector; W is padding.
static constexpr float RetailRandomVectors[256] = {
    .840796f,.813891f,.312036f,.409705f,.892850f,.503802f,.809281f,.377742f,.311328f,.108150f,.746691f,.444973f,.306975f,.958722f,.451885f,.0822420f,
    .399972f,.0812900f,.245685f,.433091f,.0911770f,.787678f,.489735f,.575681f,.429327f,.479088f,.994538f,.673963f,.423418f,.977108f,.628466f,.842047f,
    .191882f,.228921f,.785621f,.256387f,.879887f,.622279f,.801219f,.172460f,.840796f,.813891f,.312036f,.776001f,.602731f,.0128050f,.545680f,.576612f,
    .258923f,.129449f,.733609f,.776765f,.308455f,.294581f,.913658f,.844449f,.375183f,.978853f,.428443f,.131553f,.414992f,.0156550f,.590460f,.330335f,
    .995044f,.506598f,.569916f,.261539f,.526623f,.186814f,.888852f,.953245f,.429767f,.974934f,.639661f,.743165f,.669612f,.764758f,.111239f,.424083f,
    .435360f,.183351f,.118483f,.560506f,.196027f,.505871f,.896946f,.270710f,.182654f,.489446f,.113762f,.984206f,.489892f,.974144f,.658383f,.0711010f,
    .975564f,.380410f,.597662f,.466624f,.0441310f,.318927f,.403063f,.344429f,.0250070f,.491437f,.344088f,.0185720f,.832404f,.177144f,.687808f,.543193f,
    .908834f,.254218f,.350178f,.350695f,.300320f,.904002f,.716587f,.397697f,.242521f,.411378f,.0806540f,.406470f,.924259f,.488238f,.764322f,.586954f,
    .342563f,.971971f,.549566f,.963398f,.315562f,.963127f,.461316f,.909517f,.191886f,.889296f,.440722f,.951838f,.469036f,.0293320f,.665869f,.444422f,
    .741022f,.652844f,.910545f,.553683f,.266224f,.790136f,.833421f,.834226f,.908181f,.284288f,.691980f,.483448f,.417763f,.790482f,.101431f,.153960f,
    .150757f,.629250f,.166348f,.359245f,.0395060f,.353832f,.371235f,.939238f,.0973910f,.254725f,.666572f,.570285f,.773237f,.323679f,.120194f,.974246f,
    .285994f,.857065f,.223042f,.100589f,.272433f,.0720840f,.377112f,.402916f,.533814f,.314517f,.963091f,.0282740f,.153012f,.361124f,.167866f,.748453f,
    .983539f,.469407f,.623505f,.656017f,.477317f,.528396f,.00132300f,.923924f,.0666200f,.506131f,.749287f,.0504510f,.848485f,.249520f,.243450f,.405907f,
    .0369500f,.685308f,.464709f,.272810f,.380287f,.0146720f,.511236f,.595491f,.668458f,.0531240f,.351933f,.780319f,.672278f,.0311360f,.522069f,.921864f,
    .842112f,.351749f,.833138f,.100663f,.233485f,.0770540f,.490699f,.0677480f,.641836f,.961169f,.368828f,.755992f,.582643f,.627093f,.0235370f,.813861f,
    .660399f,.630621f,.0447960f,.882384f,.840796f,.813891f,.312036f,.409705f,.892850f,.503802f,.809281f,.377742f,.311328f,.108150f,.746691f,.444973f
};

static float RetailFrac(const float Value)
{
    return Value - FMath::FloorToFloat(Value);
}

static FVector RetailRandomVector(const int32 TableIndex, const float Fraction)
{
    const float F2 = Fraction * Fraction;
    const float F3 = F2 * Fraction;
    const float Weights[4] = {
        -Fraction + 2.f * F2 - F3,
        1.f - 2.f * F2 + F3,
        Fraction + F2 - F3,
        -F2 + F3
    };
    FVector Result = FVector::ZeroVector;
    for (int32 Knot = 0; Knot < 4; ++Knot)
    {
        const int32 Offset = (TableIndex + Knot) * 4;
        Result.X += RetailRandomVectors[Offset] * Weights[Knot];
        Result.Y += RetailRandomVectors[Offset + 1] * Weights[Knot];
        Result.Z += RetailRandomVectors[Offset + 2] * Weights[Knot];
    }
    return Result;
}
}

AStrandGroomActor::AStrandGroomActor()
{
    PrimaryActorTick.bCanEverTick = true;
    PrimaryActorTick.bStartWithTickEnabled = true;
    Ribbons = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("StrandRibbons"));
    SetRootComponent(Ribbons);
    Ribbons->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Ribbons->SetGenerateOverlapEvents(false);
    Ribbons->SetCanEverAffectNavigation(false);
    Ribbons->CastShadow = true;
}

void AStrandGroomActor::OnConstruction(const FTransform& Transform)
{
    Super::OnConstruction(Transform);
    RebuildGroom();
}

void AStrandGroomActor::RebuildGroom()
{
    Ribbons->ClearAllMeshSections();
    RestPositions.Reset();
    SkinnedBasePositions.Reset();
    CurrentPositions.Reset();
    PreviousPositions.Reset();
    SkinnedRootNormals.Reset();
    SkinnedRootFrameYs.Reset();
    RestLengths.Reset();
    ReferenceComponentTransforms.Reset();
    GuideOffsets.Reset();
    MeshTriangles.Reset();
    DynamicMaterial = nullptr;
    BuiltTessellation = 0;
    if (!GroomAsset || GroomAsset->Guides.IsEmpty()) return;
    for (const FStrandGroomGuide& Guide : GroomAsset->Guides)
    {
        if (Guide.ControlVertices.Num() < 2)
        {
            UE_LOG(LogTemp, Error,
                TEXT("Strand Groom %s contains a guide with fewer than two control vertices."),
                *GetNameSafe(GroomAsset));
            return;
        }
    }

    BuiltTessellation = TessellationOverride > 0
        ? FMath::Clamp(TessellationOverride, 4, 20)
        : FMath::Clamp(GroomAsset->Tessellation, 4, 20);
    for (const FStrandGroomGuide& Guide : GroomAsset->Guides)
    {
        SkinnedRootNormals.Add(Guide.RootNormal.GetSafeNormal(
            SMALL_NUMBER, FVector::UpVector));
        SkinnedRootFrameYs.Add(Guide.RootFrameY.GetSafeNormal(
            SMALL_NUMBER, FVector::RightVector));
        GuideOffsets.Add(RestPositions.Num());
        for (const FVector& Position : Guide.ControlVertices)
        {
            RestPositions.Add(Position);
            SkinnedBasePositions.Add(Position);
            CurrentPositions.Add(Position);
            PreviousPositions.Add(Position);
        }
        for (int32 Index = 1; Index < Guide.ControlVertices.Num(); ++Index)
            RestLengths.Add(FVector::Distance(
                Guide.ControlVertices[Index - 1], Guide.ControlVertices[Index]));
    }
    GuideOffsets.Add(RestPositions.Num());

    if (BindingMesh && BindingMesh->GetSkinnedAsset())
    {
        const FReferenceSkeleton& RefSkeleton =
            BindingMesh->GetSkinnedAsset()->GetRefSkeleton();
        const TArray<FTransform>& Local = RefSkeleton.GetRefBonePose();
        ReferenceComponentTransforms.SetNum(Local.Num());
        for (int32 Bone = 0; Bone < Local.Num(); ++Bone)
        {
            const int32 Parent = RefSkeleton.GetParentIndex(Bone);
            ReferenceComponentTransforms[Bone] = Parent == INDEX_NONE
                ? Local[Bone]
                : Local[Bone] * ReferenceComponentTransforms[Parent];
        }
        BuildSkinnedBasePositions();
        CurrentPositions = SkinnedBasePositions;
        PreviousPositions = SkinnedBasePositions;
    }

    const int32 GuideCount = GroomAsset->Guides.Num();
    const int32 StrandsPerClump = FMath::Clamp(GroomAsset->StrandsPerClump, 1, 64);
    const int32 RenderGuideCount = GuideCount * StrandsPerClump;
    // Retail emits L,R,L,R duplicated pairs at each live tessellation step.
    // The endpoint steps are zero-W sentinels, leaving Tessellation-2 spatial
    // samples and four projectable invocations per sample.
    const int32 SampleCount = BuiltTessellation - 2;
    const int32 VerticesPerGuide = SampleCount * 4;
    MeshTriangles.Reserve(RenderGuideCount * (SampleCount - 1) * 6);
    for (int32 RenderGuide = 0; RenderGuide < RenderGuideCount; ++RenderGuide)
    {
        const int32 Base = RenderGuide * VerticesPerGuide;
        for (int32 Segment = 0; Segment < SampleCount - 1; ++Segment)
        {
            const int32 A = Base + Segment * 4;
            const int32 B = A + 4;
            MeshTriangles.Add(A);
            MeshTriangles.Add(B);
            MeshTriangles.Add(A + 1);
            MeshTriangles.Add(A + 1);
            MeshTriangles.Add(B);
            MeshTriangles.Add(B + 1);
        }
    }
    BuildRibbonVertices();
    Ribbons->CreateMeshSection_LinearColor(
        0, MeshVertices, MeshTriangles, MeshNormals, MeshUVs,
        MeshUV1s, MeshUV2s, MeshUV3s,
        MeshColors, MeshTangents, false, false);
    if (StrandMaterial)
    {
        DynamicMaterial = UMaterialInstanceDynamic::Create(StrandMaterial, this);
        Ribbons->SetMaterial(0, DynamicMaterial);
        UpdateMaterialParameters();
    }
}

void AStrandGroomActor::BuildSkinnedBasePositions()
{
    SkinnedBasePositions = RestPositions;
    SkinnedRootNormals.Reset();
    SkinnedRootFrameYs.Reset();
    if (GroomAsset)
    {
        for (const FStrandGroomGuide& Guide : GroomAsset->Guides)
        {
            SkinnedRootNormals.Add(Guide.RootNormal.GetSafeNormal(
                SMALL_NUMBER, FVector::UpVector));
            SkinnedRootFrameYs.Add(Guide.RootFrameY.GetSafeNormal(
                SMALL_NUMBER, FVector::RightVector));
        }
    }
    if (!BindingMesh || !BindingMesh->GetSkinnedAsset()
        || ReferenceComponentTransforms.IsEmpty() || !GroomAsset)
        return;
    const FTransform WorldToActor = GetActorTransform().Inverse();
    for (int32 GuideIndex = 0; GuideIndex < GroomAsset->Guides.Num(); ++GuideIndex)
    {
        const FStrandGroomGuide& Guide = GroomAsset->Guides[GuideIndex];
        if (Guide.BoneInfluences.IsEmpty())
            continue;
        const int32 Begin = GuideOffsets[GuideIndex];
        const int32 End = GuideOffsets[GuideIndex + 1];
        FVector SkinnedNormal = FVector::ZeroVector;
        FVector SkinnedFrameY = FVector::ZeroVector;
        float FrameWeight = 0.f;
        for (const FStrandGroomBoneInfluence& Influence : Guide.BoneInfluences)
        {
            const int32 Bone = BindingMesh->GetBoneIndex(Influence.Bone);
            if (Bone == INDEX_NONE || !ReferenceComponentTransforms.IsValidIndex(Bone)
                || Influence.Weight <= 0.f)
                continue;
            const FTransform BoneWorld =
                Cast<UPoseableMeshComponent>(BindingMesh)
                ? CastChecked<UPoseableMeshComponent>(BindingMesh)
                    ->GetBoneTransformByName(Influence.Bone, EBoneSpaces::WorldSpace)
                : BindingMesh->GetBoneTransform(Bone);
            const FVector BoneLocalNormal = ReferenceComponentTransforms[Bone]
                .InverseTransformVectorNoScale(Guide.RootNormal);
            const FVector BoneLocalFrameY = ReferenceComponentTransforms[Bone]
                .InverseTransformVectorNoScale(Guide.RootFrameY);
            SkinnedNormal += WorldToActor.TransformVectorNoScale(
                BoneWorld.TransformVectorNoScale(BoneLocalNormal)) * Influence.Weight;
            SkinnedFrameY += WorldToActor.TransformVectorNoScale(
                BoneWorld.TransformVectorNoScale(BoneLocalFrameY)) * Influence.Weight;
            FrameWeight += Influence.Weight;
        }
        if (FrameWeight > SMALL_NUMBER)
        {
            SkinnedRootNormals[GuideIndex] = (SkinnedNormal / FrameWeight)
                .GetSafeNormal(SMALL_NUMBER, Guide.RootNormal.GetSafeNormal());
            // Re-orthogonalize after linear-blend skinning. Retail stores two
            // packed root axes, and the clump shader assumes a stable frame.
            const FVector Normal = SkinnedRootNormals[GuideIndex];
            const FVector Candidate = SkinnedFrameY / FrameWeight;
            SkinnedRootFrameYs[GuideIndex] = (Candidate
                - Normal * FVector::DotProduct(Candidate, Normal))
                .GetSafeNormal(SMALL_NUMBER, Guide.RootFrameY.GetSafeNormal());
        }
        for (int32 Point = Begin; Point < End; ++Point)
        {
            FVector Skinned = FVector::ZeroVector;
            float TotalWeight = 0.f;
            for (const FStrandGroomBoneInfluence& Influence : Guide.BoneInfluences)
            {
                const int32 Bone = BindingMesh->GetBoneIndex(Influence.Bone);
                if (Bone == INDEX_NONE || !ReferenceComponentTransforms.IsValidIndex(Bone)
                    || Influence.Weight <= 0.f)
                    continue;
                const FVector BoneLocal = ReferenceComponentTransforms[Bone]
                    .InverseTransformPosition(RestPositions[Point]);
                const FTransform BoneWorld =
                    Cast<UPoseableMeshComponent>(BindingMesh)
                    ? CastChecked<UPoseableMeshComponent>(BindingMesh)
                        ->GetBoneTransformByName(
                            Influence.Bone, EBoneSpaces::WorldSpace)
                    : BindingMesh->GetBoneTransform(Bone);
                const FVector World = BoneWorld.TransformPosition(BoneLocal);
                Skinned += WorldToActor.TransformPosition(World) * Influence.Weight;
                TotalWeight += Influence.Weight;
            }
            if (TotalWeight > SMALL_NUMBER)
                SkinnedBasePositions[Point] = Skinned / TotalWeight;
        }
    }
}

FVector AStrandGroomActor::SampleGuide(int32 GuideIndex, float Fraction) const
{
    const int32 Begin = GuideOffsets[GuideIndex];
    const int32 End = GuideOffsets[GuideIndex + 1];
    const int32 Count = End - Begin;
    if (Count <= 0) return FVector::ZeroVector;
    if (Count == 1) return CurrentPositions[Begin];
    const float Position = FMath::Clamp(Fraction, 0.f, 1.f) * float(Count - 1);
    const int32 Knot = FMath::FloorToInt(Position);
    const float T = Position - float(Knot);
    const FVector P0 = CurrentPositions[Begin + FMath::Clamp(Knot - 1, 0, Count - 1)];
    const FVector P1 = CurrentPositions[Begin + FMath::Clamp(Knot, 0, Count - 1)];
    const FVector P2 = CurrentPositions[Begin + FMath::Clamp(Knot + 1, 0, Count - 1)];
    const FVector P3 = CurrentPositions[Begin + FMath::Clamp(Knot + 2, 0, Count - 1)];
    const float T2 = T * T;
    const float T3 = T2 * T;
    const FVector Spline = (
        P0 * (1.f - 3.f * T + 3.f * T2 - T3)
        + P1 * (4.f - 6.f * T2 + 3.f * T3)
        + P2 * (1.f + 3.f * T + 3.f * T2 - 3.f * T3)
        + P3 * T3) / 6.f;
    const float EndWeight = 1.f - FMath::Clamp(float(Count) - Position, 0.f, 1.f);
    const FVector EndCorrected = FMath::Lerp(Spline, FMath::Lerp(P0, P1, T), EndWeight);
    const float StartWeight = 1.f - FMath::Clamp(Position, 0.f, 1.f);
    return FMath::Lerp(EndCorrected, FMath::Lerp(P1, P2, T), StartWeight);
}

void AStrandGroomActor::BuildRibbonVertices()
{
    MeshVertices.Reset();
    MeshNormals.Reset();
    MeshUVs.Reset();
    MeshUV1s.Reset();
    MeshUV2s.Reset();
    MeshUV3s.Reset();
    MeshColors.Reset();
    MeshTangents.Reset();
    if (!GroomAsset) return;
    const int32 GuideCount = GroomAsset->Guides.Num();
    const int32 StrandsPerClump = FMath::Clamp(GroomAsset->StrandsPerClump, 1, 64);
    const int32 RenderGuideCount = GuideCount * StrandsPerClump;
    const int32 SampleCount = BuiltTessellation - 2;
    const int32 VertexCount = RenderGuideCount * SampleCount * 4;
    MeshVertices.Reserve(VertexCount);
    MeshNormals.Reserve(VertexCount);
    MeshUVs.Reserve(VertexCount);
    MeshUV1s.Reserve(VertexCount);
    MeshUV2s.Reserve(VertexCount);
    MeshUV3s.Reserve(VertexCount);
    MeshColors.Reserve(VertexCount);
    MeshTangents.Reserve(VertexCount);
    for (int32 RenderGuide = 0; RenderGuide < RenderGuideCount; ++RenderGuide)
    {
        const int32 Guide = RenderGuide / StrandsPerClump;
        const int32 Child = RenderGuide % StrandsPerClump;
        const FVector Normal = SkinnedRootNormals.IsValidIndex(Guide)
            ? SkinnedRootNormals[Guide]
            : GroomAsset->Guides[Guide].RootNormal.GetSafeNormal(
                SMALL_NUMBER, FVector::UpVector);
        const FVector FrameY = SkinnedRootFrameYs.IsValidIndex(Guide)
            ? SkinnedRootFrameYs[Guide]
            : GroomAsset->Guides[Guide].RootFrameY.GetSafeNormal(
                SMALL_NUMBER, FVector::RightVector);
        for (int32 Step = 0; Step < SampleCount; ++Step)
        {
            const float Along = float(Step) / float(SampleCount - 1);
            const FVector Position = SampleGuide(Guide, Along);
            const float Delta = 1.f / float(SampleCount - 1);
            const FVector Before = SampleGuide(Guide, FMath::Max(0.f, Along - Delta));
            const FVector After = SampleGuide(Guide, FMath::Min(1.f, Along + Delta));
            const FVector Tangent =
                (After - Before).GetSafeNormal(
                    SMALL_NUMBER, FVector::ForwardVector);
            for (int32 Pair = 0; Pair < 2; ++Pair)
            for (int32 Side = 0; Side < 2; ++Side)
            {
                MeshVertices.Add(Position);
                MeshNormals.Add(Normal);
                // UV.x packs side in bit 0 and the retail clump child index
                // above it. The material decodes both without adding a second
                // vertex stream. Alpha carries the authored per-guide scale.
                MeshUVs.Add(FVector2D(float(Side + Child * 2), Along));
                MeshUV1s.Add(FVector2D(Tangent.X, Tangent.Y));
                MeshUV2s.Add(FVector2D(Tangent.Z, 0.f));
                // Retail stray placement hashes the authored guide and child indices.
                MeshUV3s.Add(FVector2D(float(Guide), 0.f));
                MeshColors.Add(FLinearColor(
                    GroomAsset->Guides[Guide].RootUV.X,
                    GroomAsset->Guides[Guide].RootUV.Y,
                    0.f,
                    GroomAsset->Guides[Guide].WidthScale));
                MeshTangents.Add(FProcMeshTangent(FrameY, false));
            }
        }
    }
}

void AStrandGroomActor::Simulate(float DeltaSeconds)
{
    if (!GroomAsset || CurrentPositions.IsEmpty() || !GetWorld()) return;
    // The captured shader works in metres. Its current input is freshly skinned
    // base geometry while the previous buffer contains last frame's simulation.
    const FVector LocalWind = GetActorTransform().InverseTransformVectorNoScale(
        WindDirection.GetSafeNormal()).GetSafeNormal();
    const float Timer = WindTimerOffset + GetWorld()->GetTimeSeconds();
    const float TimerFraction = RetailFrac(Timer * .159155f);
    for (int32 Guide = 0; Guide < GroomAsset->Guides.Num(); ++Guide)
    {
        const int32 Begin = GuideOffsets[Guide];
        const int32 End = GuideOffsets[Guide + 1];
        const int32 Count = End - Begin;
        const FVector2D RootUV = GroomAsset->Guides[Guide].RootUV;
        const float Frequency0 = WindTurbulence * 20.f + 10.f;
        const float Frequency1 = WindTurbulence * 100.f + 50.f;
        const float Noise = (
            FMath::Sin(Frequency0 * RootUV.X) + FMath::Sin(Frequency0 * RootUV.Y)
            + .5f * (FMath::Sin(Frequency1 * RootUV.X) + FMath::Sin(Frequency1 * RootUV.Y))) * .125f;
        const float PhaseTime = (Timer + .125f + Noise * .125f)
            * (WindTurbulence * 10.f + 5.f);
        const float PhaseFraction = RetailFrac(PhaseTime);
        const int32 TableIndex = FMath::TruncToInt(
            RetailFrac(PhaseTime * .0163934f) * 61.f);
        const FVector RandomVector = RetailRandomVector(TableIndex, PhaseFraction);
        const float Force = AnimationForce * .9f + .05f + Noise * .05f;
        const float BlendDenominator = 1.925f - Force * .875f;
        float Blend = BlendDenominator <= 0.f ? 0.f : FMath::Clamp(
            (.6625f - Force * .4375f) / BlendDenominator, 0.f, 1.f);
        Blend = Blend * Blend * (3.f - 2.f * Blend);
        const float Wave = FMath::Sin((Force + TimerFraction) * 6.28319f);
        const float ScalarWind = (((1.f - Blend) * Force + Blend + 1.f)
            * Wave - 1.f) * WindStrength;
        const float MaxForce = FMath::Min(
            Blend * (Force * .0125f + .0375f), WindRadiusMetres * .1f);
        const FVector Field(
            ScalarWind + LocalWind.X * MaxForce,
            LocalWind.Y * MaxForce - WindStrength,
            ScalarWind + LocalWind.Z * MaxForce);

        const FVector RootCurrentM = SkinnedBasePositions[Begin] * .01f;
        const FVector RootBaseM = RootCurrentM;
        FVector PreviousOutputM = RootCurrentM;
        FVector PreviousBaseM = RootBaseM;
        float CumulativeLengthM = 0.f;
        for (int32 Index = 0; Index < Count; ++Index)
        {
            const int32 Point = Begin + Index;
            const FVector BaseM = SkinnedBasePositions[Point] * .01f;
            const FVector CurrentM = BaseM;
            const FVector PreviousM = PreviousPositions[Point] * .01f;
            CumulativeLengthM += FVector::Distance(CurrentM, PreviousOutputM);
            const float Along = float(Index) / float(Count);
            const float Stiffness = FMath::Clamp(FMath::Pow(
                FMath::Min(.25f + .75f * Along,
                    FMath::Abs(StiffnessInverseLength * CumulativeLengthM)),
                FMath::Max(StiffnessPower, 0.f)), 0.f, 1.f);
            const FVector VelocityM = CurrentM - PreviousM;
            const float DragDenominator = Drag + .001f
                + (1.f - Drag) * 500.f * VelocityM.SizeSquared();
            FVector CandidateM = CurrentM + VelocityM
                * (-.95f * Drag * Stiffness / FMath::Max(DragDenominator, .001f));
            if (Stiffness * WindStrength > 0.f)
                CandidateM += (Field + RandomVector * WindStrength) * (Stiffness / 30.f);

            const FVector ConstraintVector = CandidateM - RootCurrentM
                - (PreviousOutputM - RootCurrentM) * .5f;
            FVector CorrectedM = CandidateM;
            const float ConstraintLengthSq = ConstraintVector.SizeSquared();
            if (ConstraintLengthSq > 0.f)
            {
                const FVector TargetVector = BaseM - RootBaseM
                    - (PreviousBaseM - RootBaseM) * .5f;
                const float TargetLength = TargetVector.Size();
                const float ConstraintLength = FMath::Sqrt(ConstraintLengthSq);
                CorrectedM += ConstraintVector
                    * ((TargetLength - ConstraintLength) / ConstraintLength);
            }
            CurrentPositions[Point] = CorrectedM * 100.f;
            PreviousOutputM = CorrectedM;
            PreviousBaseM = BaseM;
        }
    }
    PreviousPositions = CurrentPositions;
}

void AStrandGroomActor::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!GroomAsset || BuiltTessellation <= 0) return;
    BuildSkinnedBasePositions();
    Simulate(DeltaSeconds);
    BuildRibbonVertices();
    Ribbons->UpdateMeshSection_LinearColor(
        0, MeshVertices, MeshNormals, MeshUVs, MeshUV1s, MeshUV2s, MeshUV3s,
        MeshColors, MeshTangents, false);
}

void AStrandGroomActor::ResetSimulation()
{
    BuildSkinnedBasePositions();
    CurrentPositions = SkinnedBasePositions;
    PreviousPositions = SkinnedBasePositions;
    if (BuiltTessellation > 0)
    {
        BuildRibbonVertices();
        Ribbons->UpdateMeshSection_LinearColor(
            0, MeshVertices, MeshNormals, MeshUVs, MeshUV1s, MeshUV2s, MeshUV3s,
            MeshColors, MeshTangents, false);
    }
}

float AStrandGroomActor::GetMaximumDisplacementCm() const
{
    float Maximum = 0.f;
    const int32 Count = FMath::Min(CurrentPositions.Num(), SkinnedBasePositions.Num());
    for (int32 Index = 0; Index < Count; ++Index)
        Maximum = FMath::Max(Maximum,
            FVector::Distance(CurrentPositions[Index], SkinnedBasePositions[Index]));
    return Maximum;
}

FVector AStrandGroomActor::GetGuideRootWorldPosition(const int32 GuideIndex) const
{
    if (!GuideOffsets.IsValidIndex(GuideIndex)
        || !SkinnedBasePositions.IsValidIndex(GuideOffsets[GuideIndex]))
        return FVector::ZeroVector;
    return GetActorTransform().TransformPosition(
        SkinnedBasePositions[GuideOffsets[GuideIndex]]);
}

FVector AStrandGroomActor::GetGuideRootWorldNormal(const int32 GuideIndex) const
{
    if (!SkinnedRootNormals.IsValidIndex(GuideIndex))
        return FVector::ZeroVector;
    return GetActorTransform().TransformVectorNoScale(
        SkinnedRootNormals[GuideIndex]).GetSafeNormal();
}

FVector AStrandGroomActor::GetGuideRootWorldFrameY(const int32 GuideIndex) const
{
    if (!SkinnedRootFrameYs.IsValidIndex(GuideIndex))
        return FVector::ZeroVector;
    return GetActorTransform().TransformVectorNoScale(
        SkinnedRootFrameYs[GuideIndex]).GetSafeNormal();
}

void AStrandGroomActor::UpdateMaterialParameters()
{
    if (!DynamicMaterial || !GroomAsset) return;
    DynamicMaterial->SetScalarParameterValue(
        TEXT("StrandWidthScale"), FMath::Max(0.001f, StrandWidth));
    DynamicMaterial->SetScalarParameterValue(
        TEXT("Wetness"), FMath::Clamp(Wetness, 0.f, 1.f));
    DynamicMaterial->SetVectorParameterValue(TEXT("RootColor"), RootColor);
    DynamicMaterial->SetVectorParameterValue(TEXT("TipColor"), TipColor);
    DynamicMaterial->SetVectorParameterValue(
        TEXT("SceneKeyDirection"), FLinearColor(
            SceneKeyDirection.X, SceneKeyDirection.Y, SceneKeyDirection.Z, 1.f));
    DynamicMaterial->SetVectorParameterValue(TEXT("SceneKeyRadiance"), SceneKeyRadiance);
}

void AStrandGroomActor::SetStrandWeather(
    float NewWetness, float NewWindStrength)
{
    Wetness = FMath::Clamp(NewWetness, 0.f, 1.f);
    WindStrength = FMath::Max(0.f, NewWindStrength);
    UpdateMaterialParameters();
}

void AStrandGroomActor::SetStrandLighting(
    FVector KeyDirection, FLinearColor KeyRadiance)
{
    SceneKeyDirection = KeyDirection.GetSafeNormal(
        SMALL_NUMBER, FVector(.6f, .8f, 1.f).GetSafeNormal());
    SceneKeyRadiance = KeyRadiance;
    UpdateMaterialParameters();
}
